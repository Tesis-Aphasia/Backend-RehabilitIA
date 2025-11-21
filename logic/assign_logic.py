from firebase_admin import firestore
import random

db = firestore.client()


# ============================================================
# Utilidades básicas
# ============================================================

def load_exercise(exercise_id: str):
    """Carga un ejercicio VNEST desde /ejercicios_VNEST/{id}."""
    doc = db.collection("ejercicios_VNEST").document(exercise_id).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    data["id"] = doc.id
    return data


def assign_exercise_to_patient(patient_id: str, exercise_id: str):
    """
    Registra un ejercicio en /pacientes/{id}/ejercicios_asignados/.
    Detecta el tipo (VNEST o SR), carga el contexto y asigna prioridad.
    """
    try:
        base_ref = db.collection("ejercicios").document(exercise_id)
        base_doc = base_ref.get()

        if not base_doc.exists:
            raise ValueError(f"No existe el ejercicio con ID {exercise_id}")

        base_data = base_doc.to_dict()
        tipo = base_data.get("terapia")

        if not tipo:
            raise ValueError(f"El ejercicio {exercise_id} no tiene 'terapia' definida")

        # Buscar contexto según tipo
        subcollection = {
            "VNEST": "ejercicios_VNEST",
            "SR": "ejercicios_SR"
        }.get(tipo)

        context_doc = db.collection(subcollection).document(exercise_id).get()
        context = context_doc.to_dict().get("contexto") if context_doc.exists else None

        if not context:
            raise ValueError(f"No se encontró contexto para {exercise_id} ({tipo})")

        # Calcular prioridad
        asignados_ref = (
            db.collection("pacientes")
            .document(patient_id)
            .collection("ejercicios_asignados")
        )
        prioridades = [d.to_dict().get("prioridad", 0) for d in asignados_ref.stream()]
        next_priority = max(prioridades) + 1 if prioridades else 1

        asignados_ref.document(exercise_id).set({
            "id_ejercicio": exercise_id,
            "contexto": context,
            "tipo": tipo,
            "estado": "pendiente",
            "prioridad": next_priority,
            "ultima_fecha_realizado": None,
            "veces_realizado": 0,
            "fecha_asignacion": firestore.SERVER_TIMESTAMP,
            "personalizado": base_data.get("personalizado", False),
        })

    except Exception as e:
        print(f"Error al asignar ejercicio: {e}")


# ============================================================
# Selección y asignación inteligente de ejercicios VNEST
# ============================================================

def get_exercise_for_context(email: str, context: str, verbo: str):
    """
    Selecciona el ejercicio VNEST más adecuado para un paciente:
    - Prioriza ejercicios pendientes.
    - Si no hay, asigna uno nuevo del mismo verbo/contexto.
    - Si no hay nuevos, devuelve el completado más antiguo.
    Indica highlight si el ejercicio es personalizado.
    """
    try:
        patient_ref = db.collection("pacientes").document(email)

        # Ejercicios asignados en ese contexto
        assigned_docs = (
            patient_ref.collection("ejercicios_asignados")
            .where("contexto", "==", context)
            .stream()
        )
        assigned = [doc.to_dict() for doc in assigned_docs]

        pending, completed = [], []

        # Clasificar y marcar personalización
        for item in assigned:
            vn_doc = db.collection("ejercicios_VNEST").document(item["id_ejercicio"]).get()
            if not vn_doc.exists:
                continue

            vn_data = vn_doc.to_dict()
            if vn_data.get("verbo") != verbo:
                continue

            general_id = vn_data.get("id_ejercicio_general")
            personalizado = False

            if general_id:
                base_doc = db.collection("ejercicios").document(general_id).get()
                if base_doc.exists:
                    personalizado = base_doc.to_dict().get("personalizado", False)

            item["personalizado"] = personalizado
            item["highlight"] = personalizado
            item["prioridad"] = int(item.get("prioridad", 999))

            if item["estado"] == "pendiente":
                pending.append(item)
            else:
                completed.append(item)

        # Devolver pendiente de mayor prioridad
        if pending:
            chosen = sorted(pending, key=lambda x: (not x["personalizado"], x["prioridad"]))[0]
            ex = load_exercise(chosen["id_ejercicio"])
            if ex:
                ex["highlight"] = chosen["highlight"]
            return ex

        # Buscar ejercicios no asignados
        all_vnest = db.collection("ejercicios_VNEST").where("contexto", "==", context).stream()
        available = []

        for doc in all_vnest:
            info = doc.to_dict()
            info["id"] = doc.id

            if info.get("verbo") != verbo:
                continue

            if any(a["id_ejercicio"] == doc.id for a in assigned):
                continue

            general_id = info.get("id_ejercicio_general")
            personalizado = False
            tipo = "publico"

            if general_id:
                base_doc = db.collection("ejercicios").document(general_id).get()
                if base_doc.exists:
                    base_data = base_doc.to_dict()
                    tipo = base_data.get("tipo", "publico")
                    personalizado = base_data.get("personalizado", False)

            if tipo != "privado":
                info["highlight"] = personalizado
                available.append(info)

        # Asignar uno nuevo si existe
        if available:
            selected = random.choice(available)
            assign_exercise_to_patient(email, selected["id"])
            ex = load_exercise(selected["id"])
            if ex:
                ex["highlight"] = selected.get("highlight", False)
            return ex

        # Devolver completado más antiguo
        completed_with_date = [e for e in completed if e.get("ultima_fecha_realizado")]
        if completed_with_date:
            oldest = sorted(completed_with_date, key=lambda e: e["ultima_fecha_realizado"])[0]
            ex = load_exercise(oldest["id_ejercicio"])
            if ex:
                ex["highlight"] = oldest.get("personalizado", False)
            return ex

        return {
            "error": f"No hay ejercicios disponibles para el verbo '{verbo}' en el contexto '{context}'."
        }

    except Exception as e:
        return {"error": str(e)}
