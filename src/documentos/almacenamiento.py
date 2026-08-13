import os
from datetime import datetime


def construir_ruta_pdf(identificacion_cliente: str, numero_proceso: str, base_dir: str = "./data/staging") -> str:
    """
    Replica la estructura de carpetas que exige el spec para OneDrive:
    .../DebidaDiligencia/Año/Mes/[Identificacion_Cliente]/
    Por ahora escribe local; cuando se conecte Graph API, se reemplaza
    la función que ESCRIBE el archivo, no esta que arma la ruta.
    """
    ahora = datetime.now()
    carpeta = os.path.join(
        base_dir, "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", identificacion_cliente
    )
    os.makedirs(carpeta, exist_ok=True)

    numero_proceso_limpio = numero_proceso.replace("/", "-").strip()
    nombre_archivo = f"{numero_proceso_limpio}.pdf"
    return os.path.join(carpeta, nombre_archivo)


def guardar_pdf_local(pdf_bytes: bytes, identificacion_cliente: str, numero_proceso: str, base_dir: str = "./data/staging") -> str:
    """Guarda el PDF y devuelve la ruta donde quedó (para setear proceso.ruta_pdf)."""
    ruta = construir_ruta_pdf(identificacion_cliente, numero_proceso, base_dir)
    with open(ruta, "wb") as f:
        f.write(pdf_bytes)
    return ruta