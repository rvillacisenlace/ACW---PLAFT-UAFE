"""
Contador diario de clientes procesados. Persiste en un archivo JSON
simple para sobrevivir entre corridas del mismo día (si main.py se
corre varias veces en un día, el contador se acumula, no se reinicia
en cada ejecución). Se reinicia automáticamente cuando cambia la fecha.
"""
import json
import os
from datetime import date

LIMITE_DIARIO = 100
RUTA_CONTADOR = "data/contador_diario.json"


def _leer_estado() -> dict:
    if not os.path.exists(RUTA_CONTADOR):
        return {"fecha": "", "contador": 0}
    try:
        with open(RUTA_CONTADOR, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Archivo corrupto/ilegible - se reinicia en vez de tumbar el programa
        return {"fecha": "", "contador": 0}


def _guardar_estado(estado: dict) -> None:
    os.makedirs(os.path.dirname(RUTA_CONTADOR), exist_ok=True)
    with open(RUTA_CONTADOR, "w", encoding="utf-8") as f:
        json.dump(estado, f)


def obtener_contador_hoy() -> int:
    """Cuántos clientes se han procesado hoy (0 si es un día nuevo)."""
    estado = _leer_estado()
    hoy = str(date.today())
    if estado.get("fecha") != hoy:
        return 0
    return estado.get("contador", 0)


def incrementar_contador_hoy() -> int:
    """Suma 1 al contador de hoy (reinicia a 1 si es un día nuevo) y
    devuelve el nuevo total."""
    estado = _leer_estado()
    hoy = str(date.today())
    if estado.get("fecha") != hoy:
        estado = {"fecha": hoy, "contador": 0}
    estado["contador"] += 1
    _guardar_estado(estado)
    return estado["contador"]


def limite_alcanzado() -> bool:
    return obtener_contador_hoy() >= LIMITE_DIARIO