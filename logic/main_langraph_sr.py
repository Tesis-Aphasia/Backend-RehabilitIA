import os, json
from dotenv import load_dotenv
from typing import Dict, List, Optional
from typing_extensions import TypedDict
import firebase_admin
from firebase_admin import credentials, firestore
from openai import AzureOpenAI
from prompts.prompts_sr import generate_sr_prompt

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
AZURE_DEPLOYMENT = "gpt-4.1"
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
class SRState(TypedDict, total=False):
    user_id: str
    patient_profile: Dict
    cards: List[Dict]

# ==============================
# HELPERS FIRESTORE
# ==============================
import uuid

def save_sr_cards(user_id: str, cards: List[Dict]):
    col = db.collection("ejercicios_SR")

    for card in cards:
        # 🔹 Generar ID único tipo VNEST (ej. E4A2B7)
        doc_id = f"E{uuid.uuid4().hex[:6].upper()}"

        # 🔹 Datos del ejercicio SR
        sr_data = {
            "id_ejercicio_general": doc_id,
            "pregunta": card.get("stimulus", ""),
            "rta_correcta": card.get("answer", ""),
            "interval_index": 0,
            "intervals_sec" : [15, 30, 60, 120, 300],
            "success_streak": 0,
            "lapses": 0,
            "next_due": 0,
            "status": "learning",
        }

        # 🔹 Guardar en la colección de ejercicios generales
        db.collection("ejercicios").document(doc_id).set({
            "id": doc_id,
            "terapia": "SR",
            "revisado": False,
            "tipo": "privado",
            "creado_por": "IA",
            "personalizado": True,
            "referencia_base": None,
            "id_paciente": user_id,
            "descripcion_adaptado": "",
            "fecha_creacion": firestore.SERVER_TIMESTAMP,
        })

        # 🔹 Guardar el ejercicio SR específico
        col.document(doc_id).set(sr_data)

        # 🔹 Registrar el ejercicio en el paciente
        asignar_a_paciente(user_id, doc_id)

def asignar_a_paciente(user_id: str, ejercicio_id: str):
    asignados_ref = (
        db.collection("pacientes")
        .document(user_id)
        .collection("ejercicios_asignados")
    )

    asignados_ref.document(ejercicio_id).set({
        "id_ejercicio": ejercicio_id,
        "tipo": "privado",
        "estado": "pendiente",
        "fecha_asignacion": firestore.SERVER_TIMESTAMP,
    })


# ==============================
# PROMPT RUNNER
# ==============================
def parse_json(raw: str):
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start:end+1]
    return json.loads(s)

def run_prompt(prompt: str) -> Dict:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres experto en terapia del lenguaje y Spaced Retrieval."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return parse_json(content)

# ==============================
# MAIN
# ==============================
def main_langraph_sr(user_id: str, patient_profile: dict):
    prompt = generate_sr_prompt(patient_profile)
    out = run_prompt(prompt)

    cards = out.get("cards", [])
    if not cards:
        raise ValueError("El modelo no devolvió tarjetas SR")

    save_sr_cards(user_id, cards)

    # Devuelvo igual que antes para no romper nada aguas arriba
    return {"user_id": user_id, "cards": cards}

def export_graph_mermaid_manual(out_path: str = "graphs/langgraph_sr.mmd") -> str:
    mermaid = [
        "flowchart TD",
        "  START([Start]) --> build_prompt[build_prompt: genera prompt SR con perfil del paciente]",
        "  build_prompt --> call_model[call_model: invoca Azure OpenAI con prompt SR]",
        "  call_model --> parse_and_validate[parse_and_validate: limpia y valida JSON de salida]",
        "  parse_and_validate --> persist[persist: guarda tarjetas en Firestore y asigna al paciente]",
        "  persist --> END([Finish])",
    ]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(mermaid))
    return os.path.abspath(out_path)


if __name__ == "__main__":
    # ejemplo con un perfil falso
    profile = {
        "personal": {"nombre": "María", "lugar_nacimiento": "Bogotá"},
        "familia": {"hijos": ["Daniel", "Laura"], "pareja": "Carlos"},
        "rutinas": {"comida_favorita": "Ajiaco", "actividad_favorita": "Caminar"},
        "objetos": {"mascota": {"nombre": "Rocky"}},
    }
    res = main_langraph_sr("paciente123", profile)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    graph_path = export_graph_mermaid_manual()
    print(f"Mermaid graph exported to: {graph_path}")
