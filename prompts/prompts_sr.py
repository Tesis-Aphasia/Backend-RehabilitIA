import json

def generate_sr_prompt(patient_profile: dict, n: int = 5) -> str:
    """
    Genera un prompt para pedirle al modelo preguntas de Spaced Retrieval
    basadas en la información autobiográfica del paciente.
    """
    return (
        "Eres un terapeuta del lenguaje. Tu tarea es crear ejercicios de Spaced Retrieval "
        "para un paciente con afasia, usando SOLO su información autobiográfica.\n\n"
        f"Perfil del paciente:\n{json.dumps(patient_profile, ensure_ascii=False)}\n\n"
        f"Genera EXACTAMENTE {n} preguntas cortas, simples y claras en español, con su respuesta.\n"
        "Las preguntas deben ser de tipo autobiográfico (ej: '¿Cómo se llama tu hijo?', '¿Dónde naciste?').\n"
        "Formato de salida: JSON con una lista bajo la clave 'cards'. Cada card tiene:\n"
        "{ \"stimulus\": \"string\", \"answer\": \"string\", \"category\": \"string\" }\n"
        "Las categorías posibles son: 'personal', 'familia', 'rutina', 'objetos'.\n"
        "NO incluyas texto adicional ni explicaciones, solo JSON válido."
    )
