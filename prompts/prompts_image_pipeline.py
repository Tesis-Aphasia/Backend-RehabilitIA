"""
prompts_image_pipeline.py
Prompts para GPT-4.1 (extracción de palabras) y gpt-image-1.5 (generación de imágenes)
"""

# ============================================================
# PROMPTS GPT-4.1 — Extracción de palabras ilustrables
# ============================================================

SYSTEM_PROMPT_PALABRAS = """
Eres un terapeuta de lenguaje, experto en comunicación aumentativa y alternativa (AAC) y rehabilitación cognitiva.
Tu tarea es analizar ejercicios de terapia del lenguaje y decidir exactamente qué palabras o frases cortas necesitan una imagen pictográfica para apoyar la comprensión del paciente.

Criterios para incluir una palabra:
- Debe ser concreta y visualmente ilustrable (objetos, lugares, acciones, personas/roles)
- Verbos de acción físicamente observable: comer, caminar, dormir, leer, etc.
- Lugares concretos: hospital, parque, restaurante, etc.
- Objetos tangibles
- Roles o profesiones: médico, chef, terapeuta, etc.
- Se permiten frases cortas si representan un solo concepto claro (ej: "fecha de nacimiento")

Criterios para EXCLUIR una palabra:
- Nombres propios de personas (María, Juan, etc.)
- Correos electrónicos, teléfonos, contraseñas en formato literal
- Fechas en formato numérico
- Símbolos o texto técnico (@, .com, números)
- Palabras abstractas no ilustrables: razón, momento, inicio, fin, etc.
- Artículos, preposiciones, conjunciones

Criterios de selección:
- Selecciona solo palabras que realmente aporten valor visual al paciente
- NO generes palabras nuevas ni inventes conceptos
- Si una respuesta no es directamente ilustrable, omítela

Apoyo a la comprensión (importante):
- No te limites solo a la respuesta correcta
- Puedes incluir palabras adicionales si ayudan a entender la pregunta o a diferenciar opciones
- No incluyas palabras innecesarias ni redundantes

Para el tipo usa exactamente uno de: "verbo", "sujeto", "objeto", "donde"
Para el slot: usa snake_case, sin tildes, descriptivo y único dentro del ejercicio.

Responde con un JSON que tenga una sola clave "palabras" cuyo valor es una lista de objetos con exactamente estos campos: word, tipo, slot.

Ejemplo:
{"palabras": [
  {"word": "nacer", "tipo": "verbo", "slot": "pregunta_verbo"},
  {"word": "fecha de nacimiento", "tipo": "objeto", "slot": "pregunta_fecha_nacimiento"}
]}

"""


def get_user_prompt_sr(ejercicio: dict) -> str:
    ejercicio_texto = f"""
Tipo de ejercicio: SR (Spaced Repetition — pregunta y respuesta)
Pregunta: {ejercicio.get('pregunta', '')}
Respuesta correcta: {ejercicio.get('rta_correcta', '')}
"""
    instrucciones = """
Para ejercicios SR:
Para ejercicios SR:

1. Pregunta:
- Extrae el verbo principal (slot: "pregunta_verbo")
- Extrae sustantivos importantes SOLO si aparecen literalmente en la pregunta (Por ejepmplo relaciones familiares)

2. Respuesta:
- Extrae la respuesta correcta si es ilustrable y la o las palabras estan explicitamente en la respuesta(slot: "pregunta_<pregunta_normalizada>_rta")

REGLA CRÍTICA:
- NO inferir conceptos desde la respuesta
- NO convertir la respuesta en algo de la pregunta
- NO mover palabras entre pregunta y respuesta
- NO extraigas: nombres propios de personas, correos, teléfonos, contraseñas, fechas numéricas, palabras abstractas no ilustrables
"""
    return f"Analiza este ejercicio y devuelve las palabras que necesitan imagen:\n{ejercicio_texto}\n{instrucciones}"


def get_user_prompt_vnest(ejercicio: dict) -> str:
    import json
    pares_texto = json.dumps(ejercicio.get("pares", []), ensure_ascii=False, indent=2)
    ejercicio_texto = f"""
Tipo de ejercicio: VNEST (expansión de oraciones)
Verbo principal: {ejercicio.get('verbo', '')}
Pares sujeto-objeto:
{pares_texto}
"""
    instrucciones = """
Para ejercicios VNEST:
- Extrae el verbo principal (slot: "verbo")
- Para cada par (índice i): extrae sujeto (slot: "pares_<i>_sujeto"), objeto (slot: "pares_<i>_objeto")

- De las expansiones:
  - Extrae la opción correcta de "donde" si es un lugar concreto (slot: "pares_<i>_donde_correcta") y pueden ser 1 o 2 de las opciones incorrectas si ayudan a diferenciar visualmente (slot: "pares_<i>_donde_incorrecta_1", "pares_<i>_donde_incorrecta_2")

- Para las múltiples opciones incorrectas:
  - Puedes incluir palabras que pertenezcan a estas, SOLO si ayudan a diferenciar visualmente la opción correcta de las incorrectas
  - No incluyas todas automáticamente, solo las necesarias

- De "cuando" y "por_que":
  - Extrae sustantivos ilustrables de la opción correcta
  - Mantén frases completas si representan mejor el concepto
  - NO te limites a la opción correcta.
  - Extrae la opción correcta con slot exacto: "pares_<i>_cuando_correcta" o "pares_<i>_por_que_correcta"
  - Extrae al menos una opción incorrecta ilustrable con slot exacto: "pares_<i>_cuando_incorrecta_1", "pares_<i>_cuando_incorrecta_2", "pares_<i>_por_que_incorrecta_1", "pares_<i>_por_que_incorrecta_2"
  - NUNCA uses el nombre de la palabra como parte del slot
  - El slot SIEMPRE debe terminar en _correcta o _incorrecta_<número>


  - Debes seleccionar palabras de al menos 2 opciones diferentes (incluyendo la correcta y al menos una incorrecta).

- NO extraigas expresiones temporales abstractas como "al inicio de", "a la hora de"
- NO generes palabras nuevas
"""
    return f"Analiza este ejercicio y devuelve las palabras que necesitan imagen:\n{ejercicio_texto}\n{instrucciones}"


# ============================================================
# PROMPTS gpt-image-1.5 — Generación de imágenes pictográficas
# ============================================================

def get_image_prompt_verbo(word: str) -> str:
    return f"""
Crear una ilustración simple y plana que represente claramente la acción: {word}.

La imagen debe mostrar una persona realizando esta acción de forma clara y fácil de entender.
La acción debe verse en progreso y ser visualmente obvia incluso sin texto.
La acción debe ser la única actividad que la persona esté realizando en la imagen.

Reglas visuales:
- Mostrar solo una persona.
- La persona debe estar centrada en la imagen.
- Incluir únicamente los objetos necesarios para entender la acción.
- El movimiento debe representar claramente la acción.

Estilo visual:
- ilustración plana
- estilo pictograma educativo
- líneas limpias
- formas simples
- pocos colores
- un color principal dominante

Restricciones:
- fondo blanco puro
- sin texto
- sin letras
- sin números

La imagen debe ser fácil de reconocer para niños o personas en rehabilitación cognitiva.
Diseño visual similar a pictogramas usados en sistemas de comunicación aumentativa y alternativa (AAC).
"""


def get_image_prompt_sujeto(word: str) -> str:
    return f"""
Crear una ilustración simple y plana que represente a: {word}.

La imagen debe mostrar una persona que represente este rol o profesión.
La persona debe estar en posición neutral y no realizando una acción específica.
Puede incluir elementos simples que ayuden a identificar el rol.

Estilo visual:
- pictograma educativo
- líneas limpias
- formas simples
- pocos colores
- un color principal

Reglas:
- una sola persona
- persona centrada
- evitar escenas complejas

Restricciones:
- fondo blanco puro
- sin texto
- sin letras
- sin números

La imagen debe ser fácil de reconocer para niños o personas en rehabilitación cognitiva.
Diseño visual similar a pictogramas usados en sistemas de comunicación aumentativa y alternativa (AAC).
"""


def get_image_prompt_objeto(word: str) -> str:
    return f"""
Crear una ilustración educativa tipo pictograma que represente el objeto: {word}.

La imagen debe mostrar claramente el objeto principal asociado con la palabra "{word}".
El objeto debe ser el elemento visual más importante de la imagen, pero pueden aparecer
otros elementos simples que ayuden a entender mejor el objeto o su contexto.
No debe incluir personas a menos que la palabra "{word}" haga referencia directa a personas.

Jerarquía visual:
- el objeto principal debe ocupar la mayor parte de la imagen
- los elementos secundarios solo deben ayudar a identificar el objeto
- el concepto visual debe ser inmediato y fácil de reconocer

Estilo visual:
- ilustración plana
- pictograma educativo
- estilo iconográfico
- líneas limpias
- formas simples
- colores planos

Restricciones estrictas:
- fondo blanco puro
- sin texto
- sin letras
- sin números
- evitar detalles realistas complejos
- evitar sombras realistas

La imagen debe ser extremadamente clara y fácil de reconocer para niños o personas
con dificultades cognitivas. Estilo similar a pictogramas educativos AAC.
"""


def get_image_prompt_donde(word: str) -> str:
    return f"""
Crear una ilustración simple y plana que represente el lugar: {word}.

La imagen debe mostrar el entorno o escenario de este lugar.

Reglas:
- no incluir personas
- mostrar solo el entorno
- usar pocos elementos representativos del lugar
- el lugar debe ser el elemento visual más importante de la imagen
- evitar escenas complejas o con muchos detalles

Estilo visual:
- pictograma educativo
- líneas limpias
- formas simples
- pocos colores

Restricciones:
- fondo blanco puro
- sin texto
- sin letras
- sin números

La imagen debe ser clara y fácil de reconocer.
Diseño visual similar a pictogramas usados en sistemas de comunicación aumentativa y alternativa (AAC).
"""


def get_image_prompt(word: str, tipo: str) -> str:
    """Punto de entrada único — devuelve el prompt correcto según el tipo."""
    if tipo == "verbo":
        return get_image_prompt_verbo(word)
    if tipo == "sujeto":
        return get_image_prompt_sujeto(word)
    if tipo == "donde":
        return get_image_prompt_donde(word)
    return get_image_prompt_objeto(word)  # objeto es el fallback