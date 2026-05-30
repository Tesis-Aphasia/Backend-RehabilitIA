import os
import re
import base64
import requests

from dotenv import load_dotenv


from prompts.prompts_image_pipeline import get_image_prompt 

load_dotenv("env.env")

# ============================================================
# Config
# ============================================================
AZURE_ENDPOINT   = "https://invuniandesai-2.openai.azure.com/"
AZURE_DEPLOYMENT = "gpt-image-1.5"
AZURE_API_KEY    = os.getenv("AZURE_API_KEY")
API_VERSION      = "2024-02-01"

OUTPUT_DIR = "imagenes_generadas"


# ============================================================
# Normalizar nombre archivo
# ============================================================
def _normalize(word: str) -> str:
    v = word.lower().strip()
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        v = v.replace(src, dst)
    return re.sub(r"[^a-z]+", "_", v).strip("_")





# ============================================================
# Llamada API
# ============================================================
def _call_api(prompt: str) -> str:

    url = (
        f"{AZURE_ENDPOINT}openai/deployments/{AZURE_DEPLOYMENT}"
        f"/images/generations?api-version={API_VERSION}"
    )

    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AZURE_API_KEY}",
        },
        json={
            "prompt": prompt,
            "size": "1024x1024",
            "quality": "medium",
            "output_format": "png",
            "output_compression": 100,
            "n": 1,
        },
        timeout=60,
    )

    resp.raise_for_status()

    return resp.json()["data"][0]["b64_json"]

def generate(word, tipo) -> str:
    print("\nGenerando:", word, "| tipo:", tipo)
    prompt = get_image_prompt(word, tipo)
    return _call_api(prompt)



# ============================================================
# Generar imagen
# ============================================================

   


# ============================================================
# PRUEBAS LOCALES
# ============================================================
if __name__ == "__main__":

    generate("historia", "objeto")

