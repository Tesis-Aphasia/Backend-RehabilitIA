import os
import json
import re
import uuid
from typing import Dict, List, Optional
from typing_extensions import TypedDict

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from langgraph.graph import StateGraph
from openai import AzureOpenAI

from prompts.prompts_vnest import (
    generate_verb_prompt,
    verb_by_difficulty,
    pair_subject_object,
    sentence_expansion,
    generate_prompt,
)


# ============================================================
# Firebase
# ============================================================

KEY_PATH = "serviceAccountKey.json"

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()


# ============================================================
# Azure OpenAI
# ============================================================

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


# ============================================================
# State Models
# ============================================================

class ExerciseState(TypedDict, total=False):
    contexto: str
    nivel: str
    tipo: str
    creado_por: str
    verbos: List[str]
    verbos_clasificados: Dict[str, List[str]]
    verbo_seleccionado: str
    oraciones_svo: List[Dict[str, str]]
    pares: List[Dict]
    oraciones: List[Dict]
    doc_id: Optional[str]


# ============================================================
# Helpers
# ============================================================

def parse_json(raw: str):
    s = raw.strip()

    if s.startswith("```"):
        s = s.strip("`")
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start:end + 1]

    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"'", '"', s)
    s = re.sub(r",(\s*[}\]])", r"\1", s)

    try:
        return json.loads(s)
    except Exception:
        last_brace = s.rfind("}")
        if last_brace != -1:
            return json.loads(s[:last_brace + 1])
        raise


def run_prompt(prompt: str) -> Dict:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres experto en generación de ejercicios VNeST."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=2100,
        response_format={"type": "json_object"},
    )
    return parse_json(resp.choices[0].message.content)


def _validate_final(out5: dict):
    if not out5.get("verbo"):
        raise ValueError("Falta 'verbo'")
    if not isinstance(out5.get("pares"), list):
        raise ValueError("Faltan pares")
    if len(out5.get("oraciones", [])) != 10:
        raise ValueError("Debe haber 10 oraciones")


# ============================================================
# LangGraph Steps
# ============================================================

def step1_generate_verbs(state: ExerciseState) -> ExerciseState:
    out1 = run_prompt(generate_verb_prompt(state["contexto"]))
    state["verbos"] = out1["verbos"]
    return state


def step2_classify_verbs(state: ExerciseState) -> ExerciseState:
    out2 = run_prompt(verb_by_difficulty(state["contexto"], state["verbos"]))
    state["verbos_clasificados"] = out2["verbos_clasificados"]
    return state


def step3_select_pairs(state: ExerciseState) -> ExerciseState:
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
    out4 = run_prompt(sentence_expansion(state["verbo_seleccionado"], state["oraciones_svo"]))
    final_prompt = generate_prompt(out4)
    out5 = run_prompt(final_prompt)

    try:
        _validate_final(out5)
    except Exception:
        pass

    verbo_final = (out5.get("verbo") or state.get("verbo_seleccionado") or "").strip()
    if not verbo_final:
        raise ValueError("No se pudo determinar el verbo final.")

    return {
        "verbo": verbo_final,
        "pares": out5.get("pares", []),
        "oraciones": out5.get("oraciones", []),
    }


def step5_save_db(state: ExerciseState) -> ExerciseState:
    verbo = (state.get("verbo") or state.get("verbo_seleccionado") or "").strip()
    if not verbo:
        raise ValueError("State sin 'verbo' en step5.")

    doc_id = f"E{uuid.uuid4().hex[:6].upper()}"
    nivel = state.get("nivel")
    contexto = state.get("contexto")
    pares = state.get("pares", [])
    oraciones = state.get("oraciones", [])
    creado_por = state.get("creado_por", "terapeuta")
    visibilidad = state.get("tipo", "privado")

    db.collection("ejercicios").document(doc_id).set({
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
    })

    db.collection("ejercicios_VNEST").document(doc_id).set({
        "id_ejercicio_general": doc_id,
        "nivel": nivel,
        "contexto": contexto,
        "verbo": verbo,
        "pares": pares,
        "oraciones": oraciones,
    })

    return {
        "doc_id": doc_id,
        "verbo": verbo,
        "nivel": nivel,
        "contexto": contexto,
        "pares": pares,
        "oraciones": oraciones,
    }


# ============================================================
# Graph
# ============================================================

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


# ============================================================
# Entry
# ============================================================

def main_langraph_vnest(contexto: str, nivel: str, creado_por: str, tipo: str) -> dict:
    workflow = build_graph()
    initial_state = {
        "contexto": contexto,
        "nivel": nivel,
        "creado_por": creado_por,
        "tipo": tipo,
    }
    final = workflow.invoke(initial_state)

    return {
        "id": final.get("doc_id"),
        "verbo": final.get("verbo") or final.get("verbo_seleccionado"),
        "nivel": final.get("nivel"),
        "context_hint": final.get("contexto"),
        "reviewed": final.get("reviewed", False),
        "pares": final.get("pares", []),
        "oraciones": final.get("oraciones", []),
    }


# ============================================================
# Manual Test
# ============================================================

if __name__ == "__main__":
    build_graph()

    test_result = main_langraph_vnest(
        "Un hospital",
        "facil",
        "terapeuta_demo",
        "privado"
    )

    print(json.dumps(test_result, indent=2, ensure_ascii=False))
