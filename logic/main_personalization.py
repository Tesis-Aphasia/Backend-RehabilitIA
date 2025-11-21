import os, json, uuid
from dotenv import load_dotenv
from typing import Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore
from openai import AzureOpenAI
from prompts.prompts_personalization import generate_personalization_prompt
from logic.assign_logic import assign_exercise_to_patient

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
# FIRESTORE HELPERS
# ==============================
def get_exercise_base(exercise_id: str) -> Dict[str, Any]:
    """Obtiene un ejercicio base desde /ejercicios/{exercise_id} y su contenido extendido."""

    doc_ref = db.collection("ejercicios").document(exercise_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"Ejercicio base '{exercise_id}' no encontrado.")

    base_data = doc.to_dict()
    tipo = base_data.get("terapia")
    if not tipo:
        raise ValueError(f"El ejercicio '{exercise_id}' no tiene campo 'terapia' definido.")

    tipo = tipo.upper()
    extra_data = {}

    if tipo == "VNEST":
        extra_ref = db.collection("ejercicios_VNEST").document(exercise_id)
    elif tipo == "SR":
        extra_ref = db.collection("ejercicios_SR").document(exercise_id)
    else:
        raise ValueError(f"Terapia desconocida: {tipo}")

    extra_doc = extra_ref.get()
    if extra_doc.exists:
        extra_data = extra_doc.to_dict()

    return {**base_data, **extra_data}

def save_personalized_exercise(exercise_data: Dict[str, Any]) -> str:
    """Guarda el ejercicio personalizado tanto en /ejercicios como en la subcolección específica."""

    # --- 1️⃣ Crear ID único
    doc_id = f"E{uuid.uuid4().hex[:6].upper()}"
    exercise_data["id"] = doc_id

    # --- 2️⃣ Datos generales del ejercicio
    general_data = {
        "id": doc_id,
        "terapia": exercise_data.get("terapia"),
        "revisado": False,
        "tipo": "privado",
        "creado_por": exercise_data.get("creado_por"),  # terapeuta_uid o "ia"
        "personalizado": True,
        "referencia_base": exercise_data.get("referencia_base"),
        "id_paciente": exercise_data.get("id_paciente"),  # 👈 ahora UID del paciente
        "descripcion_adaptado": exercise_data.get("descripcion_adaptado", ""),
        "contexto": exercise_data.get("contexto"),
        "fecha_creacion": firestore.SERVER_TIMESTAMP,
    }

    # --- 3️⃣ Guardar en la colección general
    db.collection("ejercicios").document(doc_id).set(general_data)

    # --- 4️⃣ Guardar en la colección específica
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

    print(f"✅ Ejercicio personalizado guardado: {doc_id}")
    return doc_id

# ==============================
# OPENAI RUNNER
# ==============================
def run_prompt(prompt: str) -> Dict[str, Any]:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres un terapeuta experto en lenguaje y afasia. Debes personalizar ejercicios de terapia."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=3000,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content.strip()

    print("\n" + "=" * 80)
    print("🔍 RAW MODEL RESPONSE (Azure OpenAI):")
    print(content)
    print("=" * 80 + "\n")

    return json.loads(content)

# ==============================
# MAIN PERSONALIZATION
# ==============================
def main_personalization(user_id: str, exercise_id: str, patient_profile: Dict[str, Any]):
    """Genera un ejercicio personalizado para un paciente (UID) y lo guarda en Firestore."""

    base_exercise = get_exercise_base(exercise_id)
    prompt = generate_personalization_prompt(base_exercise, patient_profile, user_id)
    result = run_prompt(prompt)

    # --- Asegurar metadatos importantes ---
    result["id_paciente"] = user_id
    result["referencia_base"] = exercise_id
    result["creado_por"] = "IA"  # o terapeuta_uid si aplica
    result["personalizado"] = True
    result["contexto"] = base_exercise.get("contexto") or base_exercise.get("context_hint")

    # --- Guardar en Firestore
    new_id = save_personalized_exercise(result)

    # --- Asignar el ejercicio al paciente
    assign_exercise_to_patient(user_id, new_id)

    return {"ok": True, "saved_id": new_id, "personalized": result}

# ==============================
# TEST (EJEMPLO)
# ==============================
if __name__ == "__main__":
    patient_id = "UID_DE_EJEMPLO"  # 👈 ahora debe ser el UID real del paciente
    exercise_id = "6ixn7LFB6rQ1cxTPQYEL"

    doc_ref = db.collection("pacientes").document(patient_id)  # 👈 corregido
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"No existe el documento del paciente {patient_id}")

    profile = doc.to_dict()
    print("Perfil cargado desde Firestore:")
    print(json.dumps(profile, indent=2, ensure_ascii=False))

    res = main_personalization(patient_id, exercise_id, profile)

    print("\nResultado de la personalización:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
