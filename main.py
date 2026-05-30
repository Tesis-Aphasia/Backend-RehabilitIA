from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from firebase_admin import firestore

# Importaciones de tus funciones auxiliares
from logic.image_generator_service import generate_images_for_exercise, _extract_words_with_gpt, _normalize_key
from logic.main_langraph_vnest import main_langraph_vnest
from logic.main_langraph_sr import main_langraph_sr
from logic.main_personalization import main_personalization
from logic.main_profile_structure import main_profile_structure
from logic.image_generator_service import _get_or_generate, _normalize_key

app = FastAPI()
db = firestore.client()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ContextGeneratePayload(BaseModel):
    context: str
    nivel: str
    creado_por: str
    tipo: str 

class SRPayload(BaseModel):
    user_id: str
    profile: dict

class PersonalizePayload(BaseModel):
    user_id: str
    exercise_id: str
    profile: dict

class ProfileStructurePayload(BaseModel):
    user_id: str
    raw_text: str

class ImageGeneratePayload(BaseModel):
    exercise_id: str
    terapia: str  

# ========================
#  ENDPOINTS
# ========================

@app.get("/")
def read_root():
    return {"Hello": "World"}

# --- Generar ejercicio VNEST
@app.post("/context/generate")
def create_exercise(payload: ContextGeneratePayload):
    response = main_langraph_vnest(payload.context, payload.nivel, payload.creado_por, payload.tipo)
    return response

# --- Generar tarjetas SR
@app.post("/spaced-retrieval/")
def create_sr_cards(payload: SRPayload):
    print("Payload recibido:", payload)
    response = main_langraph_sr(payload.user_id, payload.profile)
    return response

# --- Personalizar ejercicio
@app.post("/personalize-exercise/")
def personalize_exercise(payload: PersonalizePayload):
    response = main_personalization(payload.user_id, payload.exercise_id, payload.profile)
    return response

# --- Estructurar perfil
@app.post("/profile/structure/")
def structure_profile(payload: ProfileStructurePayload):
    response = main_profile_structure(payload.user_id, payload.raw_text)
    print("Respuesta generada:", response)
    return response

@app.post("/images/generate")
def generate_images(payload: ImageGeneratePayload):
    result = generate_images_for_exercise(payload.exercise_id, payload.terapia)
    return result

    

# ── Preview: ahora usa GPT-4.1 ──────────
@app.post("/images/preview")
def preview_images(payload: ImageGeneratePayload):
    """
    Llama a GPT-4.1 para saber qué palabras necesitan imagen,
    luego verifica cuáles ya existen en Firebase.
    NO genera imágenes — solo muestra el plan.
    """
    coleccion = "ejercicios_VNEST" if payload.terapia == "VNEST" else "ejercicios_SR"
    ref = db.collection(coleccion).document(payload.exercise_id)
    doc = ref.get()
 
    if not doc.exists:
        return {"error": f"Ejercicio {payload.exercise_id} no encontrado"}
 
    ejercicio = doc.to_dict()
 
    # GPT-4.1 decide qué palabras necesitan imagen
    try:
        words = _extract_words_with_gpt(ejercicio, payload.terapia)
    except Exception as e:
        return {"error": f"Error al extraer palabras con GPT: {str(e)}"}
 
    # Para cada palabra, verifica si ya existe imagen en Firebase
    resultado = []
    for item in words:
        key = _normalize_key(item["word"])
        img_doc = db.collection("imagenes").document(key).get()
        ya_existe = img_doc.exists
        url_existente = img_doc.to_dict().get("url") if ya_existe else None
 
        resultado.append({
            "word": item["word"],
            "tipo": item["tipo"],
            "slot": item["slot"],
            "key": key,
            "ya_existe_en_firebase": ya_existe,
            "url_existente": url_existente,
            "accion": "reutilizar" if ya_existe else "generar",
        })
 
    resumen = {
        "total": len(resultado),
        "a_generar": sum(1 for r in resultado if r["accion"] == "generar"),
        "a_reutilizar": sum(1 for r in resultado if r["accion"] == "reutilizar"),
    }
 
    return {
        "exercise_id": payload.exercise_id,
        "terapia": payload.terapia,
        "resumen": resumen,
        "palabras": resultado,
    }

import firebase_admin.storage as fb_storage

@app.post("/images/{image_key}/delete")
def delete_image(image_key: str, exercise_id: str, terapia: str):

    try:
        db = firestore.client()
        
        # 1. Borrar de Storage
        bucket = fb_storage.bucket("apphasia-7a930.firebasestorage.app")
        blob = bucket.blob(f"imagenes/{image_key}.png")
        if blob.exists():
            blob.delete()

        # 2. Borrar de colección imagenes
        db.collection("imagenes").document(image_key).delete()

        # 3. Limpiar el slot en el documento del ejercicio
        coleccion = "ejercicios_VNEST" if terapia == "VNEST" else "ejercicios_SR"
        ref = db.collection(coleccion).document(exercise_id)
        doc_snap = ref.get()
        if doc_snap.exists:
            imagenes = doc_snap.to_dict().get("imagenes", {})
            nuevas = {k: v for k, v in imagenes.items() if v.get("key") != image_key}
            ref.update({"imagenes": nuevas})

        return {"ok": True, "deleted": image_key}

    except Exception as e:
        return {"error": str(e)}


@app.post("/exercises/{exercise_id}/delete")
def delete_exercise(exercise_id: str, terapia: str):
    try:
        coleccion = "ejercicios_VNEST" if terapia == "VNEST" else "ejercicios_SR"
        ref = db.collection(coleccion).document(exercise_id)
        doc_snap = ref.get()

        if doc_snap.exists:
            imagenes = doc_snap.to_dict().get("imagenes", {})
            bucket = fb_storage.bucket("apphasia-7a930.firebasestorage.app")

            for slot, img in imagenes.items():
                key = img.get("key")
                if key:
                    # Borrar de Storage
                    blob = bucket.blob(f"imagenes/{key}.png")
                    if blob.exists():
                        blob.delete()
                    # Borrar de colección imagenes
                    db.collection("imagenes").document(key).delete()

        # Borrar documentos del ejercicio
        ref.delete()
        db.collection("ejercicios").document(exercise_id).delete()

        return {"ok": True, "deleted": exercise_id}

    except Exception as e:
        return {"error": str(e)}
    
class SingleImagePayload(BaseModel):
    exercise_id: str
    terapia: str
    slot: str
    word: str
    tipo: str

@app.post("/images/generate-single")
def generate_single_image(payload: SingleImagePayload):
    try:
        

        url = _get_or_generate(payload.word, payload.tipo)
        if not url:
            return {"ok": False, "error": f"No se pudo generar la imagen para '{payload.word}'"}

        imagen = {
            "word": payload.word,
            "url": url,
            "key": _normalize_key(payload.word),
        }

        # Guardar el slot en el documento del ejercicio
        coleccion = "ejercicios_VNEST" if payload.terapia == "VNEST" else "ejercicios_SR"
        ref = db.collection(coleccion).document(payload.exercise_id)
        ref.update({f"imagenes.{payload.slot}": imagen})

        return {"ok": True, "imagen": imagen}

    except Exception as e:
        return {"ok": False, "error": str(e)}
    

@app.post("/images/regenerate")
def regenerate_images(payload: ImageGeneratePayload):
    """Fuerza regeneración del mapa de imágenes ignorando caché de slots."""
    db = firestore.client()
    coleccion = "ejercicios_VNEST" if payload.terapia == "VNEST" else "ejercicios_SR"
    ref = db.collection(coleccion).document(payload.exercise_id)
    doc = ref.get()

    if not doc.exists:
        return {"error": f"Ejercicio {payload.exercise_id} no encontrado"}

    ejercicio = doc.to_dict()

    try:
        words = _extract_words_with_gpt(ejercicio, payload.terapia)
    except Exception as e:
        return {"error": f"Error al extraer palabras con GPT: {str(e)}"}

    if not words:
        return {"error": "GPT no encontró palabras ilustrables"}

    # Reutiliza imágenes existentes en Firebase pero reconstruye el mapa con slots correctos
    imagenes_map = {}
    for item in words:
        url = _get_or_generate(item["word"], item["tipo"])
        if url:
            imagenes_map[item["slot"]] = {
                "word": item["word"],
                "url": url,
                "key": _normalize_key(item["word"]),
            }

    # Sobreescribe el mapa completo
    ref.update({"imagenes": imagenes_map})

    return {
        "ok": True,
        "exercise_id": payload.exercise_id,
        "terapia": payload.terapia,
        "palabras_extraidas": len(words),
        "con_imagen": len(imagenes_map),
        "imagenes": imagenes_map,
    }