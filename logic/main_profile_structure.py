# main_profile_structure.py
import os, json
from dotenv import load_dotenv
from typing import Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore
from openai import AzureOpenAI
from prompts.prompts_profile_structure import generate_profile_structure_prompt

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
# OPENAI RUNNER
# ==============================
def run_prompt(prompt: str) -> Dict[str, Any]:
    client = get_client()
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Eres un asistente experto en estructurar perfiles clínicos de pacientes con afasia."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1500,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content.strip()
    return json.loads(content)

def export_graph_mermaid_manual(out_path: str = "graphs/langgraph_profile_structure.mmd") -> str:
    mermaid = [
        "flowchart TD",
        "  START([Start]) --> generate_prompt[generate_prompt: crea prompt con texto no estructurado]",
        "  generate_prompt --> call_model[call_model: Azure OpenAI devuelve perfil estructurado JSON]",
        "  call_model --> persist_profile[persist_profile: (opcional) guarda perfil en Firestore]",
        "  persist_profile --> END([Finish])",
    ]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(mermaid))
    return os.path.abspath(out_path)

# ==============================
# MAIN FUNCTION
# ==============================
def main_profile_structure(user_id: str, raw_text: str):
    """
    Recibe texto no estructurado del paciente y devuelve un perfil organizado
    con secciones: personal, familia, rutinas y objetos.
    """

    prompt = generate_profile_structure_prompt(raw_text, user_id)
    result = run_prompt(prompt)

    # # (Opcional) Guardar una copia estructurada del perfil
    # doc_ref = db.collection("perfiles_IA").document(user_id)
    # doc_ref.set({
    #     "user_id": user_id,
    #     "raw_text": raw_text,
    #     "structured_profile": result,
    #     "timestamp": firestore.SERVER_TIMESTAMP
    # })

    return {"ok": True, "user_id": user_id, "structured_profile": result}

if __name__ == "__main__":
    # ejemplo con texto no estructurado falso
    fake_user_id = "user_12345"
    fake_raw_text = (
        "Mi nombre es Juan Pérez. Tengo 65 años y vivo con mi esposa María en Bogotá. "
        "Antes de mi accidente, trabajaba como profesor de matemáticas. "
        "Me gusta leer libros de historia y pasar tiempo con mis nietos. "
        "Mis rutinas diarias incluyen caminar por el parque y escuchar música clásica. "
        "Algunos objetos importantes para mí son mi reloj antiguo y mis gafas de lectura."
    )

    res = main_profile_structure(fake_user_id, fake_raw_text)

    print("\nResultado del perfil estructurado:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

    graph_path = export_graph_mermaid_manual()
    print(f"Mermaid graph exported to: {graph_path}")



