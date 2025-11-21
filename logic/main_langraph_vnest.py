import os, json
from dotenv import load_dotenv
from typing import Dict, List, Optional
from typing_extensions import TypedDict
import firebase_admin
from firebase_admin import credentials, firestore
from langgraph.graph import StateGraph
from langchain_core.tools import tool
from openai import AzureOpenAI
from prompts.prompts_vnest import (
    generate_verb_prompt,
    verb_by_difficulty,
    pair_subject_object,
    sentence_expansion,
    generate_prompt,
)
import uuid

# ==============================
# FIREBASE CONFIG
# ==============================
KEY_PATH = "serviceAccountKey.json"
if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_PATH)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ==============================
# AZURE CONFIG
# ==============================
load_dotenv("env.env")
AZURE_ENDPOINT = "https://invuniandesai-2.openai.azure.com/"
AZURE_DEPLOYMENT = "gpt-4.1"     # tu deployment
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_API_VERSION = "2024-12-01-preview"

def get_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=AZURE_API_KEY,
        azure_endpoint=AZURE_ENDPOINT,
        api_version=AZURE_API_VERSION,
    )

# ==============================
# STATE
# ==============================
class ExerciseState(TypedDict, total=False):
    contexto: str
    nivel: str
    tipo: str  # 👈 agregado
    creado_por: str   # 👈 agregado (para claridad)
    verbos: List[str]
    verbos_clasificados: Dict[str, List[str]]
    verbo_seleccionado: str
    oraciones_svo: List[Dict[str, str]]
    pares: List[Dict]
    oraciones: List[Dict]
    doc_id: Optional[str]
# ==============================
# HELPERS FIRESTORE
# ==============================
def _normalize_for_front(doc_id: str, data: dict) -> dict:
    return {
        "id": doc_id,
        "verbo": data.get("verbo", ""),
        "nivel": data.get("nivel", ""),
        "context_hint": data.get("context_hint", ""),
        "reviewed": bool(data.get("reviewed", False)),
        "pares": data.get("pares", []),
        "oraciones": data.get("oraciones", []),
    }


# ==============================
# PROMPT RUNNER
# ==============================
import re, json

def parse_json(raw: str):
    s = raw.strip()

    # Si viene dentro de ```
    if s.startswith("```"):
        s = s.strip("`")
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start:end+1]

    # Limpieza defensiva: eliminar secuencias ilegales
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r'“|”', '"', s)  # reemplazar comillas curvas
    s = re.sub(r"'", '"', s)    # reemplazar comillas simples si hay JSON inconsistente
    s = re.sub(r',(\s*[}\]])', r'\1', s)  # quitar comas finales sobrantes

    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        print("Error al decodificar JSON:", e)
        print("Contenido truncado:", s[:1000])
        # Intenta recortar hasta el último corchete cerrado
        last_brace = s.rfind("}")
        if last_brace != -1:
            try:
                return json.loads(s[:last_brace+1])
            except Exception:
                pass
        raise e


def run_prompt(prompt: str) -> Dict:
    client = get_client()
    print("\n" + "="*60)

    print("Prompt enviado:\n", prompt[:1000], "...")  # imprimimos máx 1000 chars
    print("="*60)

    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres experto en terapias del lenguaje y generación de ejercicios VNeST."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=2100,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    print("📥 Respuesta cruda:\n", content)
    print("="*60 + "\n")

    return parse_json(content)


def _validate_final(out5: dict):
    if "verbo" not in out5 or not out5["verbo"]:
        raise ValueError("Falta 'verbo'")
    if "pares" not in out5 or not isinstance(out5["pares"], list):
        raise ValueError("Faltan pares")
    if "oraciones" not in out5 or len(out5["oraciones"]) != 10:
        raise ValueError("Debe haber 10 oraciones")

# ==============================
# NODOS
# ==============================
def step1_generate_verbs(state: ExerciseState) -> ExerciseState:
    """Genera 7 verbos transitivos a partir del contexto proporcionado."""
    out1 = run_prompt(generate_verb_prompt(state["contexto"]))
    state["verbos"] = out1["verbos"]
    return state

def step2_classify_verbs(state: ExerciseState) -> ExerciseState:
    """Clasifica los verbos generados en fácil, medio y difícil."""
    out2 = run_prompt(verb_by_difficulty(state["contexto"], state["verbos"]))
    state["verbos_clasificados"] = out2["verbos_clasificados"]
    return state

def step3_select_pairs(state: ExerciseState) -> ExerciseState:
    """Selecciona un verbo del nivel indicado y genera 3 oraciones SVO disyuntivas."""
    out3 = run_prompt(
        pair_subject_object(
            state["contexto"],
            state["verbos_clasificados"],
            nivel=state["nivel"],
            n_oraciones=3,
        )
    )
    state["verbo_seleccionado"] = out3["verbo_seleccionado"]
    state["oraciones_svo"] = out3["oraciones"]
    return state

def step4_expand_sentences(state: ExerciseState) -> ExerciseState:
    """Genera expansiones y 10 oraciones; fija 'verbo' en el state pase lo que pase."""
    out4 = run_prompt(sentence_expansion(state["verbo_seleccionado"], state["oraciones_svo"]))
    final_prompt = generate_prompt(out4)
    out5 = run_prompt(final_prompt)

    # Aunque falle la validación, no queremos romper la cadena
    try:
        _validate_final(out5)
    except Exception as e:
        print("_validate_final falló:", e)

    # Verbo final robusto
    verbo_final = (out5.get("verbo") or state.get("verbo_seleccionado") or "").strip()
    if not verbo_final:
        raise ValueError("No se pudo determinar 'verbo' en step4.")

    # Devuelve solo el delta con 'verbo'
    return {
        "verbo": verbo_final,
        "pares": out5.get("pares", []),
        "oraciones": out5.get("oraciones", []),
    }


def step5_save_db(state: ExerciseState) -> ExerciseState:
    """
    Guarda directamente el nuevo ejercicio generado por el terapeuta.
    Crea documentos en:
      - 'ejercicios' (información general)
      - 'ejercicios_VNEST' (contenido extendido)
    """

    verbo_final = (state.get("verbo") or state.get("verbo_seleccionado") or "").strip()
    if not verbo_final:
        raise ValueError("State sin 'verbo' en step5_save_db.")

    nivel = state.get("nivel")
    contexto = state.get("contexto")
    pares = state.get("pares", [])
    oraciones = state.get("oraciones", [])
    creado_por = state.get("creado_por", "terapeuta_anonimo")
    visibilidad = state.get("tipo", "privado")  # o "publico"

    # Generar ID único tipo E###
    doc_id = f"E{uuid.uuid4().hex[:6].upper()}"

    # 1️⃣ Guardar información general
    general_doc = {
        "id": doc_id,
        "terapia": "VNEST",
        "revisado": False,
        "tipo": visibilidad,
        "creado_por": creado_por,
        "personalizado": False,
        "referencia_base": None,
        "id_paciente": None,
        "descripcion_adaptado": "",
        "fecha_creacion": firestore.SERVER_TIMESTAMP,
    }
    db.collection("ejercicios").document(doc_id).set(general_doc)

    # 2️⃣ Guardar contenido extendido (ejercicios_VNEST)
    vnest_doc = {
        "id_ejercicio_general": doc_id,
        "nivel": nivel,
        "contexto": contexto,
        "verbo": verbo_final,
        "oraciones": oraciones,
        "pares": pares
    }
    db.collection("ejercicios_VNEST").document(doc_id).set(vnest_doc)

    print(f"✅ Nuevo ejercicio VNeST guardado correctamente: {doc_id}")

    return {
        "doc_id": doc_id,
        "verbo": verbo_final,
        "nivel": nivel,
        "contexto": contexto,
        "reviewed": False,
        "pares": pares,
        "oraciones": oraciones,
    }

# ==============================
# GRAFO
# ==============================

def export_graph_mermaid_manual(out_path: str = "langgraph_vnest.mmd") -> str:
    """
    Genera un diagrama Mermaid del flujo VNeST sin depender de APIs internas de LangGraph.
    """
    mermaid = [
        "flowchart TD",
        "  START([Start]) --> step1_generate_verbs[step1_generate_verbs: genera 7 verbos]",
        "  step1_generate_verbs --> step2_classify_verbs[step2_classify_verbs: clasifica verbos]",
        "  step2_classify_verbs --> step3_select_pairs[step3_select_pairs: selecciona verbo y 3 SVO]",
        "  step3_select_pairs --> step4_expand_sentences[step4_expand_sentences: expansiones + 10 oraciones]",
        "  step4_expand_sentences --> step5_save_db[step5_save_db: lee/guarda en Firestore]",
        "  step5_save_db --> END([Finish])",
    ]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(mermaid))
    return os.path.abspath(out_path)


def build_graph():
    graph = StateGraph(ExerciseState)

    graph.add_node("step1_generate_verbs", step1_generate_verbs)
    graph.add_node("step2_classify_verbs", step2_classify_verbs)
    graph.add_node("step3_select_pairs", step3_select_pairs)
    graph.add_node("step4_expand_sentences", step4_expand_sentences)
    graph.add_node("step5_save_db", step5_save_db)

    graph.add_edge("step1_generate_verbs", "step2_classify_verbs")
    graph.add_edge("step2_classify_verbs", "step3_select_pairs")
    graph.add_edge("step3_select_pairs", "step4_expand_sentences")
    graph.add_edge("step4_expand_sentences", "step5_save_db")

    graph.set_entry_point("step1_generate_verbs")
    graph.set_finish_point("step5_save_db")

    return graph.compile()

# ==============================
# MAIN
# ==============================
def main_langraph_vnest(contexto: str, nivel: str, creado_por: str, tipo: str) -> dict:
    workflow = build_graph()
    initial_state = {"contexto": contexto, "nivel": nivel, "creado_por": creado_por, "tipo": tipo}
    final_state = workflow.invoke(initial_state)

    return {
        "id": final_state.get("doc_id", "fake_id"),
        "verbo": final_state.get("verbo") or final_state.get("verbo_seleccionado"),
        "nivel": final_state.get("nivel"),
        "context_hint": final_state.get("contexto"),
        "reviewed": final_state.get("reviewed", False),
        "pares": final_state.get("pares", []),
        "oraciones": final_state.get("oraciones", []),
    }


if __name__ == "__main__":
    build_graph()
    path = export_graph_mermaid_manual("graphs/langgraph_vnest.mmd")
    print("✅ Mermaid exportado en:", path)

    resultado = main_langraph_vnest("Un hospital")
    #print(json.dumps(resultado, indent=2, ensure_ascii=False))
