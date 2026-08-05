"""
Normalización de texto para búsquedas en los portales gubernamentales.
Requisito explícito del spec: eliminar tildes y eñes antes de enviar
la consulta por nombre (Escenario 2, Reglas para Personas Naturales).
"""
import re
import unicodedata


def normalizar_texto_busqueda(texto: str) -> str:
    """
    'Torres Gordillo Diego Patricio' -> 'TORRES GORDILLO DIEGO PATRICIO'
    'Núñez Peña' -> 'NUNEZ PENA'
    'José  #123 Müller' -> 'JOSE MULLER'
    'Pérez-Gómez' -> 'PEREZ GOMEZ'
    """
    texto_descompuesto = unicodedata.normalize("NFKD", texto)
    sin_diacriticos = "".join(c for c in texto_descompuesto if not unicodedata.combining(c))
    sin_enie = sin_diacriticos.replace("ñ", "n").replace("Ñ", "N")
    en_mayusculas = sin_enie.upper()
    # Guion -> espacio ANTES de filtrar, para no pegar apellidos compuestos
    # (ej. "PEREZ-GOMEZ" debe quedar "PEREZ GOMEZ", no "PEREZGOMEZ").
    con_guion_como_espacio = en_mayusculas.replace("-", " ")
    solo_letras_y_espacios = re.sub(r"[^A-Z ]", "", con_guion_como_espacio)
    return re.sub(r" {2,}", " ", solo_letras_y_espacios).strip()