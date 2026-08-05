"""
src/core/logger.py

Log de auditoría estructurado (JSON Lines - una línea = un evento).
Cumple el requisito del spec (sección "Gestión de Logs y Auditoría"):
registra fecha/hora, cliente, usuario, IP, resultado, sitio consultado,
y ruta de la evidencia, por cada intento de sitio por cliente.
"""
import json
import os
import socket
from datetime import datetime

from src.core.models import LogEntry, ResultadoConsulta

DIR_LOGS = "./data/logs"


def _obtener_ip_local() -> str:
    """
    Obtiene la IP local de la máquina que ejecuta el proceso (spec pide
    explícitamente "Dirección IP desde donde se ejecuta el proceso").
    No es la IP pública - es la IP de red local del equipo, suficiente
    para trazabilidad interna de auditoría.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "IP_NO_DETECTADA"


def registrar_evento(
    cliente_identificacion: str,
    cliente_nombre: str,
    usuario_proceso: str,
    resultado: ResultadoConsulta,
    sitio_web: str,
    ruta_evidencia: str = "",
    detalle: str = "",
) -> None:
    """
    Escribe un evento de auditoría como una línea JSON en el archivo del
    día. Se llama una vez por cada intento de sitio por cliente (Sitio 1,
    Sitio 2), no solo al final del procesamiento completo del cliente.
    """
    os.makedirs(DIR_LOGS, exist_ok=True)

    entrada = LogEntry(
        fecha_hora=datetime.now(),
        cliente_identificacion=cliente_identificacion,
        cliente_nombre=cliente_nombre,
        usuario_proceso=usuario_proceso,
        ip_origen=_obtener_ip_local(),
        resultado=resultado,
        sitio_web=sitio_web,
        ruta_evidencia=ruta_evidencia,
        detalle=detalle,
    )

    nombre_archivo = f"auditoria_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    ruta_completa = os.path.join(DIR_LOGS, nombre_archivo)

    with open(ruta_completa, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada.to_dict(), ensure_ascii=False) + "\n")