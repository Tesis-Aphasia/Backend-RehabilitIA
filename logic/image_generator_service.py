import os
import re
import json
from openai import AzureOpenAI
from firebase_admin import firestore, storage
from logic.image_generator import generate, OUTPUT_DIR
from prompts.prompts_image_pipeline import (
    SYSTEM_PROMPT_PALABRAS,
    get_user_prompt_sr,
    get_user_prompt_vnest,
)


# ============================================================
# Config Azure GPT-4.1
# ============================================================
GPT_ENDPOINT    = "https://invuniandesai-2.openai.azure.com/"
GPT_DEPLOYMENT  = "gpt-4.1"
GPT_API_KEY     = os.getenv("AZURE_API_KEY")
GPT_API_VERSION = "2024-12-01-preview"


def _get_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=GPT_API_KEY,
        azure_endpoint=GPT_ENDPOINT,
        api_version=GPT_API_VERSION,
    )


# ============================================================
# Normalizar key para Firebase y nombre de archivo
# ============================================================
def _normalize_key(word: str) -> str:
    v = word.lower().strip()
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        v = v.replace(src, dst)
    return re.sub(r"[^a-z]+", "_", v).strip("_")


# ============================================================
# GPT-4.1 extrae qué palabras necesitan imagen
# ============================================================
def _extract_words_with_gpt(ejercicio: dict, terapia: str) -> list[dict]:

    # ── Usa prompts centralizados ──
    if terapia == "SR":
        prompt_usuario = get_user_prompt_sr(ejercicio)
    else:
        prompt_usuario = get_user_prompt_vnest(ejercicio)

    prompt_sistema = SYSTEM_PROMPT_PALABRAS

    client = _get_client()
    resp = client.chat.completions.create(
        model=GPT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user",   "content": prompt_usuario},
        ],
        temperature=0,
        max_tokens=800,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    data = json.loads(content)

    raw_words = data.get("palabras", data) if isinstance(data, dict) else data

    result = []
    for item in raw_words:
        if "word" in item and "tipo" in item and "slot" in item:
            result.append({
                "word": str(item["word"]).strip(),
                "tipo": str(item["tipo"]).strip(),
                "slot": str(item["slot"]).strip(),
            })

    return result


# ============================================================
# Genera o reutiliza imagen desde Firebase
# ============================================================
def _get_or_generate(word: str, tipo: str) -> str | None:
    """
    Busca si ya existe imagen en la colección 'imagenes'.
    Si no existe, la genera con gpt-image-1.5, la sube a Firebase Storage y guarda la URL.
    """
    db = firestore.client()
    key = _normalize_key(word)
    ref = db.collection("imagenes").document(key)
    doc = ref.get()

    if doc.exists:
        return doc.to_dict().get("url")

    # Genera la imagen con el modelo de imágenes existente
    generate(word, tipo)

    filename = f"{key}.png"
    local_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(local_path):
        return None

    # Sube a Firebase Storage
    bucket = storage.bucket("apphasia-7a930.firebasestorage.app")
    blob = bucket.blob(f"imagenes/{filename}")
    blob.upload_from_filename(local_path, content_type="image/png")
    blob.make_public()
    url = blob.public_url

    # Guarda en colección 'imagenes' para reutilizar en futuros ejercicios
    ref.set({
        "word": word,
        "key": key,
        "tipo": tipo,
        "url": url,
        "generada_en": firestore.SERVER_TIMESTAMP,
    })

    return url


# ============================================================
# Función principal
# ============================================================
def generate_images_for_exercise(exercise_id: str, terapia: str) -> dict:
    """
    1. Lee el ejercicio de Firestore
    2. Usa GPT-4.1 para extraer qué palabras necesitan imagen
    3. Genera o reutiliza imágenes para cada palabra
    4. Guarda el mapa de imágenes en el ejercicio
    5. Si ya estaba revisado, lo aprueba automáticamente
    """
    db = firestore.client()

    coleccion = "ejercicios_VNEST" if terapia == "VNEST" else "ejercicios_SR"
    ref = db.collection(coleccion).document(exercise_id)
    doc = ref.get()

    if not doc.exists:
        return {"error": f"Ejercicio {exercise_id} no encontrado en {coleccion}"}

    ejercicio = doc.to_dict()

    # ── Paso 1: GPT-4.1 decide qué palabras necesitan imagen ──
    try:
        words = _extract_words_with_gpt(ejercicio, terapia)
    except Exception as e:
        return {"error": f"Error al extraer palabras con GPT: {str(e)}"}

    if not words:
        return {"error": "GPT no encontró palabras ilustrables en este ejercicio"}

    # ── Paso 2: genera o reutiliza imagen para cada palabra ──
    imagenes_map = {}
    for item in words:
        url = _get_or_generate(item["word"], item["tipo"])
        if url:
            imagenes_map[item["slot"]] = {
                "word": item["word"],
                "url": url,
                "key": _normalize_key(item["word"]),
            }

    # ── Paso 3: guarda el mapa en el ejercicio ──
    ref.update({"imagenes": imagenes_map})


    return {
        "ok": True,
        "exercise_id": exercise_id,
        "terapia": terapia,
        "palabras_extraidas": len(words),
        "con_imagen": len(imagenes_map),
        "sin_imagen": len(words) - len(imagenes_map),
        "imagenes": imagenes_map,
    }