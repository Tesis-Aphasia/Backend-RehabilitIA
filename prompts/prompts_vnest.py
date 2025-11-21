import json
from typing import List

# ---------- Prompts ----------

def generate_verb_prompt(contexto: str) -> str:
    # Prompt 1: 7 verbos transitivos específicos
    return (
        f"Dado el siguiente contexto: '{contexto}'. "
        "Genera una lista de exactamente 7 verbos transitivos que cumplan: "
        "0) Deben ser verbos que puedan claramente usarse en el contexto dado; "
        "1) Requieren complemento directo; 2) Son cotidianos y familiares; "
        "3) No son genéricos (evita 'hacer', 'tener', 'llevar'); "
        "4) Son diferentes entre sí; 5) En infinitivo; 6) Mezcla de dificultades. "
        "Responde SOLO con JSON válido, sin texto adicional. "
        'Formato: {\"contexto\":\"string\",\"verbos\":[\"v1\",\"v2\",\"v3\",\"v4\",\"v5\",\"v6\",\"v7\"]}'
    )

def verb_by_difficulty(contexto: str, verbos: List[str]) -> str:
    # Prompt 2: clasificar por dificultad
    return (
        "Toma este JSON y clasifica los verbos por dificultad. "
        "Responde SOLO con JSON válido, sin texto adicional. "
        f'Entrada: {{\"contexto\":\"{contexto}\",\"verbos\":{json.dumps(verbos, ensure_ascii=False)}}} '
        "Reglas de clasificación: "
        "Fácil = 1–2 sílabas, muy comunes y fáciles de pronunciar; "
        "Medio = 2–3 sílabas y dificultad léxica intermedia; "
        "Difícil = 3+ sílabas o mayor complejidad fonética/léxica. "
        "Distribución equilibrada (p. ej., 2/3/2). "
        'Salida (solo JSON): {\"contexto\":\"string\",\"verbos_clasificados\":{\"facil\":[...],\"medio\":[...],\"dificil\":[...]}}'
    )

def pair_subject_object(contexto: str, verbos_clasificados: dict, nivel: str, n_oraciones: int = 3) -> str:
    """
    verbos_clasificados: dict con llaves "facil" | "medio" | "dificil"
    nivel: "facil" | "medio" | "dificil"
    n_oraciones: cuántas oraciones disyuntivas generar (por defecto 3)
    """
    return (
        "PROMPT 3:\n\n"
        f"Contexto: {contexto}\n"
        f"Verbos clasificados: {verbos_clasificados}\n"
        f"Nivel solicitado: {nivel}\n\n"
        "Toma un ÚNICO verbo del nivel indicado y genera oraciones en español siguiendo estas reglas:\n"
        f"- Cantidad: exactamente {n_oraciones} oraciones simples (sujeto + verbo + objeto) usando SIEMPRE el MISMO verbo.\n"
        "- Disyuntivas entre sí: cada sujeto debe vincularse a un objeto que no pueda usarse con otro sujeto de la lista; si intercambias sujeto u objeto entre oraciones y sigue teniendo sentido, la oración es inválida y debe reemplazarse.\n"
        "- Especificidad máxima: las oraciones deben ser tan concretas y únicas que sea imposible intercambiar sujeto y objeto sin perder el sentido.\n"
        "- Variedad: oraciones en contextos/temas distintos.\n"
        "- Conjugación y gramática correctas (presente del indicativo por defecto). Sin pronombres ni nombres propios.\n"
        "- Sujeto: rol/profesión/entidad típicamente **agente** del verbo elegido.\n"
        "- Objeto: persona/objeto/documento típicamente **paciente** o **resultado** del verbo elegido.\n\n"
        "Reglas de PROTOTIPICIDAD (obligatorias):\n"
        "1) Compatibilidad verbo–sujeto: el SUJETO debe ser un agente habitual del verbo.\n"
        "2) Compatibilidad verbo–objeto: el OBJETO debe ser una entidad canónica del verbo.\n"
        "3) Evita combinaciones inter-dominio débiles o atípicas.\n"
        "4) Cobertura de tipos de OBJETO en el conjunto: usa tres tipos distintos.\n"
        "5) Prohibido usar sujetos u objetos genéricos ('persona', 'cosa', etc.).\n"
        f"6) Exactamente UNA oración debe estar directamente relacionada con el contexto '{contexto}'.\n\n"
        "Salida obligatoria: SOLO JSON válido.\n"
        "Formato de salida:\n"
        "{"
        f"\"nivel\":\"{nivel}\","
        "\"verbo_seleccionado\":\"string\","
        "\"oraciones\":["
        "{\"oracion\":\"string\",\"sujeto\":\"string\",\"objeto\":\"string\"}"
        "]}"
    )

def sentence_expansion(verbo: str, oraciones: list[dict]) -> str:
    return (
        "PROMPT 4:\n"
        "Toma el siguiente verbo y las oraciones (con sujeto y objeto) y genera expansiones específicas para cada par.\n"
        f"VERBO: {verbo}\n"
        f"ORACIONES: {oraciones}\n\n"
        "Instrucciones:\n"
        "- Para CADA oración, desarrolla 3 interrogantes: ¿Dónde?, ¿Cuándo? y ¿Por qué?.\n"
        "- Cada interrogante debe tener exactamente 4 opciones y solo 1 opción correcta.\n"
        "- Las opciones deben ser concretas y específicas al par (sujeto–verbo–objeto).\n"
        "- Mantén coherencia semántica con el verbo y las oraciones.\n"
        "- Además, agrega una explicación corta (máx. 20 palabras) para CADA opción, indicando por qué es correcta o incorrecta.\n"
        "- Ejemplo: 'opcion': 'En la cocina', 'explicacion': 'El chef suele trabajar en la cocina, por eso es correcta.'\n"
        "- IMPORTANTE: No uses comillas dentro de las explicaciones. En lugar de eso, usa comillas simples (' ').\n"
        "- Responde SOLO con JSON válido.\n\n"
        "Formato requerido:\n"
        '{'
        f'"verbo":"{verbo}",'
        '"pares":['
        '{"sujeto":"string","objeto":"string","expansiones":{'
        '"donde":{"opciones":["string","string","string","string"],"opcion_correcta":"string", "explicaciones":["string","string","string","string"]},'
        '"cuando":{"opciones":["string","string","string","string"],"opcion_correcta":"string", "explicaciones":["string","string","string","string"]},'
        '"por_que":{"opciones":["string","string","string","string"],"opcion_correcta":"string", "explicaciones":["string","string","string","string"]}'
        "}}]}"
    )

def generate_prompt(json_prev: dict) -> str:
    return (
        "PROMPT 5:\n"
        "Toma el siguiente JSON y AGRÉGALE una última parte llamada \"oraciones\". "
        "No elimines ni cambies ninguna clave existente. Devuelve SOLO JSON válido.\n\n"
        f"JSON de entrada:\n{json.dumps(json_prev, ensure_ascii=False)}\n\n"
        "Requisitos para \"oraciones\":\n"
        "- Usa el MISMO verbo del JSON de entrada.\n    "
        "- Crea EXACTAMENTE 10 oraciones simples (SVC).\n"
        "- Mezcla correctas e incorrectas.\n"
        "- Cada una: {\"oracion\":\"string\",\"correcta\":true|false}.\n\n"
        "Formato requerido:\n"
        "{"
        "  \"verbo\": \"string\","
        "  \"pares\": [ { \"sujeto\": \"string\", \"objeto\": \"string\", \"expansiones\": { ... } } ],"
        "  \"oraciones\": [ { \"oracion\": \"string\", \"correcta\": true, \"explicacion\": \"string\" } ]"
        "}"
    )
