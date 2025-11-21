from firebase_admin import firestore
import random

db = firestore.client()

# ============================================================
# Funciones de apoyo
# ============================================================

def load_exercise(exercise_id: str):
    """Carga el contenido del ejercicio desde /ejercicios_VNEST/{id}"""
    doc = db.collection("ejercicios_VNEST").document(exercise_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def assign_exercise_to_patient(patient_id: str, exercise_id: str):
    """
    Crea el registro en /patients/{id}/ejercicios_asignados/,
    buscando automáticamente el contexto según el tipo de ejercicio.
    """
    try:
        # Buscar el ejercicio base para saber su tipo
        exercise_doc = db.collection("ejercicios").document(exercise_id).get()
        if not exercise_doc.exists:
            raise ValueError(f"No existe el ejercicio con ID {exercise_id}")

        exercise_data = exercise_doc.to_dict()
        tipo = exercise_data.get("terapia")

        if not tipo:
            raise ValueError(f"El ejercicio {exercise_id} no tiene campo 'tipo' definido")

        # Buscar el contexto según el tipo
        context = None
        if tipo == "VNEST":
            sub_doc = db.collection("ejercicios_VNEST").document(exercise_id).get()
            if sub_doc.exists:
                context = sub_doc.to_dict().get("contexto")
        elif tipo == "SR":
            sub_doc = db.collection("ejercicios_SR").document(exercise_id).get()
            if sub_doc.exists:
                context = sub_doc.to_dict().get("contexto")

        if not context:
            raise ValueError(f"No se encontró el contexto para el ejercicio {exercise_id} (tipo {tipo})")

        # Calcular la prioridad del nuevo ejercicio
        col_ref = (
            db.collection("pacientes")
            .document(patient_id)
            .collection("ejercicios_asignados")
        )
        docs = col_ref.stream()
        priorities = [d.to_dict().get("prioridad", 0) for d in docs]
        next_priority = max(priorities) + 1 if priorities else 1

        # Detectar si es personalizado
        personalizado = exercise_data.get("personalizado", False)

        # Crear el documento en la subcolección del paciente
        col_ref.document(exercise_id).set({
            "id_ejercicio": exercise_id,
            "contexto": context,
            "tipo": tipo,
            "estado": "pendiente",
            "prioridad": next_priority,
            "ultima_fecha_realizado": None,
            "veces_realizado": 0,
            "fecha_asignacion": firestore.SERVER_TIMESTAMP,
            "personalizado": personalizado,
        })

        print(f"Ejercicio {exercise_id} asignado correctamente al paciente {patient_id}")

    except Exception as e:
        print(f"Error al asignar ejercicio: {e}")


# ============================================================
# Función principal con lógica de highlight
# ============================================================

def get_exercise_for_context(email: str, context: str, verbo: str):
    """
    Obtiene o asigna un ejercicio VNEST según el verbo y contexto.
    - Busca ejercicios pendientes del paciente.
    - Si no hay, asigna uno nuevo desde ejercicios_VNEST.
    - Si tampoco hay nuevos, devuelve el más antiguo completado.
    Agrega 'highlight' = True si el ejercicio es personalizado.
    """
    try:
        patient_ref = db.collection("pacientes").document(email)

        # Obtener todos los ejercicios asignados del contexto
        assigned_docs = (
            patient_ref.collection("ejercicios_asignados")
            .where("contexto", "==", context)
            .stream()
        )
        assigned_list = [doc.to_dict() for doc in assigned_docs]

        # Filtrar por verbo y agregar personalización
        pending, completed = [], []
        for e in assigned_list:
            vn_doc = db.collection("ejercicios_VNEST").document(e["id_ejercicio"]).get()
            if not vn_doc.exists:
                continue
            vn_data = vn_doc.to_dict()
            if vn_data.get("verbo") != verbo:
                continue

            general_id = vn_data.get("id_ejercicio_general")
            personalizado = False
            if general_id:
                ex_doc = db.collection("ejercicios").document(general_id).get()
                if ex_doc.exists:
                    personalizado = ex_doc.to_dict().get("personalizado", False)

            e["personalizado"] = personalizado
            e["highlight"] = personalizado
            e["prioridad"] = int(e.get("prioridad", 999))

            if e["estado"] == "pendiente":
                pending.append(e)
            else:
                completed.append(e)

        # Ordenar pendientes: personalizados primero, luego por prioridad
        pending_sorted = sorted(
            pending, key=lambda x: (not x["personalizado"], x["prioridad"])
        )
        if pending_sorted:
            chosen = pending_sorted[0]
            print("Devolviendo ejercicio pendiente existente")
            ex = load_exercise(chosen["id_ejercicio"])
            if ex:
                ex["highlight"] = chosen.get("highlight", False)
            return ex

        # Buscar ejercicios VNEST no asignados para el verbo
        all_docs = db.collection("ejercicios_VNEST").where("contexto", "==", context).stream()
        available = []
        for doc in all_docs:
            data = doc.to_dict()
            data["id"] = doc.id
            if data.get("verbo") != verbo:
                continue
            if any(a["id_ejercicio"] == doc.id for a in assigned_list):
                continue

            # Revisar tipo y personalización
            general_id = data.get("id_ejercicio_general")
            tipo = "publico"
            personalizado = False
            if general_id:
                ex_doc = db.collection("ejercicios").document(general_id).get()
                if ex_doc.exists:
                    base = ex_doc.to_dict()
                    tipo = base.get("tipo", "publico")
                    personalizado = base.get("personalizado", False)

            if tipo != "privado":
                data["highlight"] = personalizado
                available.append(data)

        # Asignar uno nuevo si hay disponibles
        if available:
            choice = random.choice(available)
            new_ex_id = choice["id"]
            print(f"Asignando nuevo ejercicio {new_ex_id} al paciente {email}")
            assign_exercise_to_patient(email, new_ex_id)
            ex = load_exercise(new_ex_id)
            if ex:
                ex["highlight"] = choice.get("highlight", False)
            return ex

        # Si no hay pendientes ni nuevos, devolver el completado más antiguo
        completed_valid = [e for e in completed if e.get("ultima_fecha_realizado")]
        if completed_valid:
            old_ex = sorted(completed_valid, key=lambda e: e["ultima_fecha_realizado"])[0]
            print("Devolviendo ejercicio completado más antiguo")
            ex = load_exercise(old_ex["id_ejercicio"])
            if ex:
                ex["highlight"] = old_ex.get("personalizado", False)
            return ex

        # Si no hay ninguno disponible
        print("No hay ejercicios disponibles para este verbo y contexto")
        return {
            "error": f"No hay ejercicios disponibles para el verbo '{verbo}' en el contexto '{context}'."
        }

    except Exception as e:
        print(f"Error en get_exercise_for_context: {e}")
        return {"error": str(e)}
