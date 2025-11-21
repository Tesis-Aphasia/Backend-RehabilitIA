# prompts_profile_structure.py
def generate_profile_structure_prompt(raw_text: str, user_id: str) -> str:
    """
    Prompt para convertir texto libre o transcripción del paciente en un perfil estructurado
    con secciones: personal, familia, rutinas y objetos.
    """
    return f"""
Eres un asistente experto en estructurar información personal y clínica de pacientes con afasia.
Recibirás un texto libre con información autobiográfica y tu tarea será transformarlo en un JSON
estructurado con los siguientes campos. El campo de 'tipo_relacion' de 'familia' debe ser alguno de estos: ["Cónyuge/Pareja", "Hijo/a", "Padre/Madre", "Hermano/a", "Otro"].
El campo 'tipo_relacion' de 'objetos' puede ser libre.
En la descripción de familia, no menciones el tipo de relación ya mencionado en 'tipo_relacion'.

Estructura esperada del JSON: 

{{
  "personal": {{
    "nombre": "",
    "fecha_nacimiento": "",
    "lugar_nacimiento": "",
    "ciudad_residencia": ""
  }},
  "familia": [
    {{"nombre": "", "tipo_relacion": "", "descripcion": ""}}
  ],
  "rutinas": [
    {{"titulo": "", "descripcion": ""}}
  ],
  "objetos": [
    {{"nombre": "", "tipo_relacion": "", "descripcion": ""}}
  ]
}}

Instrucciones:
- Usa SOLO la información presente en el texto.
- Si algún campo no se menciona, déjalo vacío o con lista vacía.
- Mantén la coherencia semántica entre campos (por ejemplo, no pongas una ciudad como nombre de persona).
- Si el texto menciona varias personas, objetos o actividades, inclúyelos en las listas correspondientes.
- Devuelve ÚNICAMENTE JSON válido, sin explicaciones ni texto adicional.

ID del paciente: {user_id}

Texto recibido:
\"\"\"{raw_text}\"\"\"
"""
