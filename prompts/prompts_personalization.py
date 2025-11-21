import json
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds

def _firestore_default(o):
    """Permite serializar fechas de Firestore al usar json.dumps."""
    if isinstance(o, DatetimeWithNanoseconds):
        return o.isoformat()
    # Si en el futuro Firestore devuelve datetime nativo, también lo manejamos:
    import datetime
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    raise TypeError(f"Type {type(o)} not serializable")


def generate_personalization_prompt(base_exercise: dict, patient_profile: dict, user_id: str) -> str:
    """
    Construye el prompt para personalizar un ejercicio base con información del paciente.
    Maneja correctamente tipos de Firestore (DatetimeWithNanoseconds).
    """

    return f"""
Eres un terapeuta experto en afasia y personalización de ejercicios de lenguaje.

Tienes un ejercicio base y el perfil de un paciente.
Tu tarea es adaptar el contenido del ejercicio al contexto del paciente,
manteniendo la estructura y los campos originales.

Perfil del paciente:
{json.dumps(patient_profile, ensure_ascii=False, indent=2, default=_firestore_default)}

Ejercicio base:
{json.dumps(base_exercise, ensure_ascii=False, indent=2, default=_firestore_default)}

Instrucciones:
1. Reemplaza nombres genéricos ("el agricultor", "la persona", "el cliente") 
   por miembros de la familia, lugares, rutinas o intereses del paciente.
2. En la sección de pares sujeto-verbo-objeto: cambia ÚNICAMENTE 1 sujeto y/o 1 objeto
   para que reflejen el contexto del paciente. Estos cambios deben ser coherentes y
   los pares deben seguir teniendo sentido en relacion con el verbo.
3. En la sección de oraciones: adapta ÚNICAMENTE 3 oraciones para que reflejen el contexto del paciente.
   Mantén las demás oraciones sin cambios.
3. No cambies el nivel ni el tipo del ejercicio.
4. Devuelve un JSON con la misma estructura, pero con el contenido adaptado.
5. Incluye estos campos adicionales:
   - "id_paciente": "{user_id}"
   - "personalizado": true
   - "referencia_base": "{base_exercise.get('id', '')}"
   - "descripcion_adaptado": breve explicación de cómo se adaptó.
6. No cambies el contexto original: debe mantenerse igual a "{base_exercise.get('context_hint')}".
    """
