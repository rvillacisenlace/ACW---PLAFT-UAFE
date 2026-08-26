import os
from datetime import datetime


def construir_ruta_pdf(identificacion_cliente: str, numero_proceso: str, carpeta_sitio: str, base_dir: str = "./data/staging", subcarpeta: str = "") -> str:
    ahora = datetime.now()
    partes_carpeta = [base_dir, "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", identificacion_cliente]
    if subcarpeta:
        partes_carpeta.append(subcarpeta)
    partes_carpeta.append(carpeta_sitio)
    carpeta = os.path.join(*partes_carpeta)
    os.makedirs(carpeta, exist_ok=True)

    numero_proceso_limpio = numero_proceso.replace("/", "-").strip()
    nombre_archivo = f"{numero_proceso_limpio}.pdf"
    return os.path.join(carpeta, nombre_archivo)


def guardar_pdf_local(pdf_bytes: bytes, identificacion_cliente: str, numero_proceso: str, carpeta_sitio: str, base_dir: str = "./data/staging", subcarpeta: str = "") -> str:
    ruta = construir_ruta_pdf(identificacion_cliente, numero_proceso, carpeta_sitio, base_dir, subcarpeta)
    with open(ruta, "wb") as f:
        f.write(pdf_bytes)
    return ruta