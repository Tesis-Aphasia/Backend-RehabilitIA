import os
import json
import uuid
from typing import Dict, List
from typing_extensions import TypedDict

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from openai import AzureOpenAI

from prompts.prompts_sr import generate_sr_prompt


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
# State models
# ============================================================

class SRState(TypedDict, total=False):
    user_id: str
    patient_profile: Dict
    cards: List[Dict]


# ============================================================
# Firestore helpers
# ============================================================

def asignar_a_paciente(user_id: str, ejercicio_id: str):
    db.collection("pacientes") \
      .document(user_id) \
      .collection("ejercicios_asignados") \
      .document(ejercicio_id) \
      .set({
            "id_ejercicio": ejercicio_id,
            "tipo": "privado",
            "estado": "pendiente",
            "fecha_asignacion": firestore.SERVER_TIMESTAMP,
        })


def save_sr_cards(user_id: str, cards: List[Dict]):
    col_sr = db.collection("ejercicios_SR")
    col_general = db.collection("ejercicios")

    for card in cards:
        # ID estilo VNEST
        doc_id = f"E{uuid.uuid4().hex[:6].upper()}"

        sr_data = {
            "id_ejercicio_general": doc_id,
            "pregunta": card.get("stimulus", ""),
            "rta_correcta": card.get("answer", ""),
            "interval_index": 0,
            "intervals_sec": [15, 30, 60, 120, 300],
            "success_streak": 0,
            "lapses": 0,
            "next_due": 0,
            "status": "learning",
        }

        col_general.document(doc_id).set({
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

        col_sr.document(doc_id).set(sr_data)
        asignar_a_paciente(user_id, doc_id)


# ============================================================
# Prompt runner
# ============================================================

def parse_json(raw: str):
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start:end + 1]
    return json.loads(s)


def run_prompt(prompt: str) -> Dict:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres experto en Spaced Retrieval."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    return parse_json(resp.choices[0].message.content)


# ============================================================
# Main workflow
# ============================================================

def main_langraph_sr(user_id: str, patient_profile: dict):
    prompt = generate_sr_prompt(patient_profile)
    result = run_prompt(prompt)

    cards = result.get("cards", [])
    if not cards:
        raise ValueError("El modelo no generó tarjetas SR.")

    save_sr_cards(user_id, cards)

    return {"user_id": user_id, "cards": cards}


# ============================================================
# Mermaid export
# ============================================================

def export_graph_mermaid_manual(out_path: str = "graphs/langgraph_sr.mmd") -> str:
    mermaid = [
        "flowchart TD",
        "  START([Start]) --> build_prompt[build_prompt: genera prompt SR]",
        "  build_prompt --> call_model[call_model: invoca Azure OpenAI]",
        "  call_model --> parse_and_validate[parse_and_validate: procesa JSON]",
        "  parse_and_validate --> persist[persist: guarda tarjetas en Firestore]",
        "  persist --> END([Finish])",
    ]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(mermaid))

    return os.path.abspath(out_path)


# ============================================================
# Manual test
# ============================================================

if __name__ == "__main__":
    sample_profile = {
        "personal": {"nombre": "María", "lugar_nacimiento": "Bogotá"},
        "familia": {"hijos": ["Daniel", "Laura"], "pareja": "Carlos"},
        "rutinas": {"comida_favorita": "Ajiaco", "actividad_favorita": "Caminar"},
        "objetos": {"mascota": {"nombre": "Rocky"}},
    }

    result = main_langraph_sr("paciente123", sample_profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    graph_path = export_graph_mermaid_manual()
    print("Mermaid graph exported to:", graph_path)
