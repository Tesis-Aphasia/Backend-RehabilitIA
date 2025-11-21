import os
import json
import uuid
from typing import Dict, Any

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from openai import AzureOpenAI

from prompts.prompts_personalization import generate_personalization_prompt
from logic.assign_logic import assign_exercise_to_patient


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
# Firestore Helpers
# ============================================================

def get_exercise_base(exercise_id: str) -> Dict[str, Any]:
    """Obtiene un ejercicio general y su contenido extendido."""
    base_ref = db.collection("ejercicios").document(exercise_id)
    base_doc = base_ref.get()

    if not base_doc.exists:
        raise ValueError(f"Ejercicio '{exercise_id}' no encontrado.")

    base_data = base_doc.to_dict()
    terapia = base_data.get("terapia")

    if not terapia:
        raise ValueError(f"El ejercicio '{exercise_id}' no tiene campo 'terapia'.")

    terapia = terapia.upper()

    if terapia == "VNEST":
        extra_ref = db.collection("ejercicios_VNEST").document(exercise_id)
    elif terapia == "SR":
        extra_ref = db.collection("ejercicios_SR").document(exercise_id)
    else:
        raise ValueError(f"Terapia no soportada: {terapia}")

    extra_doc = extra_ref.get()
    extra = extra_doc.to_dict() if extra_doc.exists else {}

    return {**base_data, **extra}


def save_personalized_exercise(exercise_data: Dict[str, Any]) -> str:
    """Guarda un ejercicio personalizado en las colecciones correspondientes."""
    doc_id = f"E{uuid.uuid4().hex[:6].upper()}"
    exercise_data["id"] = doc_id

    general_data = {
        "id": doc_id,
        "terapia": exercise_data.get("terapia"),
        "revisado": False,
        "tipo": "privado",
        "creado_por": exercise_data.get("creado_por"),
        "personalizado": True,
        "referencia_base": exercise_data.get("referencia_base"),
        "id_paciente": exercise_data.get("id_paciente"),
        "descripcion_adaptado": exercise_data.get("descripcion_adaptado", ""),
        "contexto": exercise_data.get("contexto"),
        "fecha_creacion": firestore.SERVER_TIMESTAMP,
    }

    db.collection("ejercicios").document(doc_id).set(general_data)

    terapia = exercise_data.get("terapia")

    if terapia == "VNEST":
        vnest_data = {
            "id_ejercicio_general": doc_id,
            "contexto": exercise_data.get("contexto"),
            "nivel": exercise_data.get("nivel"),
            "oraciones": exercise_data.get("oraciones", []),
            "pares": exercise_data.get("pares", []),
            "verbo": exercise_data.get("verbo", ""),
        }
        db.collection("ejercicios_VNEST").document(doc_id).set(vnest_data)

    elif terapia == "SR":
        db.collection("ejercicios_SR").document(doc_id).set(exercise_data)

    else:
        raise ValueError(f"Terapia desconocida: {terapia}")

    return doc_id


# ============================================================
# Prompt Runner
# ============================================================

def run_prompt(prompt: str) -> Dict[str, Any]:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un terapeuta experto en lenguaje y afasia. "
                    "Debes personalizar ejercicios de terapia."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=3000,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content.strip())


# ============================================================
# Personalization Workflow
# ============================================================

def main_personalization(user_id: str, exercise_id: str, patient_profile: Dict[str, Any]):
    """Genera un ejercicio personalizado basado en un ejercicio existente."""
    base = get_exercise_base(exercise_id)
    prompt = generate_personalization_prompt(base, patient_profile, user_id)
    result = run_prompt(prompt)

    result["id_paciente"] = user_id
    result["referencia_base"] = exercise_id
    result["creado_por"] = "IA"
    result["personalizado"] = True
    result["contexto"] = base.get("contexto") or base.get("context_hint")

    new_id = save_personalized_exercise(result)

    assign_exercise_to_patient(user_id, new_id)

    return {"ok": True, "saved_id": new_id, "personalized": result}


# ============================================================
# Manual Test
# ============================================================

if __name__ == "__main__":
    patient_id = "UID_DE_EJEMPLO"
    exercise_id = "6ixn7LFB6rQ1cxTPQYEL"

    doc = db.collection("pacientes").document(patient_id).get()
    if not doc.exists:
        raise ValueError(f"No existe paciente {patient_id}")

    profile = doc.to_dict()
    res = main_personalization(patient_id, exercise_id, profile)

    print(json.dumps(res, indent=2, ensure_ascii=False))
