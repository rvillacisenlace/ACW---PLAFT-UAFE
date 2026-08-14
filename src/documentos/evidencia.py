import hashlib
import os
from datetime import datetime
from playwright.sync_api import Page
from PIL import Image, ImageDraw


def capturar_evidencia(
    page: Page, identificacion_cliente: str, sitio: str,
    base_dir: str = "./data/staging", pagina_completa: bool = True
) -> dict:
    """
    Captura screenshot de la página actual, agrega overlay de fecha/hora
    (lectura humana), y calcula hash SHA-256 (integridad real, para que
    cualquier alteración posterior del archivo sea detectable).

    pagina_completa=False: usa captura de solo el viewport visible, no
    "página completa". Necesario para sitios donde el contenido incluye
    un visor de PDF embebido (extensión nativa de Chrome) - el cálculo
    de altura de "página completa" no considera correctamente ese
    visor, dejando una franja negra en la parte inferior de la captura
    (confirmado con el sitio de Cobertura de Salud).
    """
    ahora = datetime.now()
    carpeta = os.path.join(
        base_dir, "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", identificacion_cliente
    )
    os.makedirs(carpeta, exist_ok=True)

    timestamp_archivo = ahora.strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"evidencia_{sitio}_{timestamp_archivo}.png"
    ruta_archivo = os.path.join(carpeta, nombre_archivo)

    page.screenshot(path=ruta_archivo, full_page=pagina_completa)

    # Overlay de fecha/hora - para lectura humana rápida del abogado
    timestamp_legible = ahora.strftime("%Y-%m-%d %H:%M:%S")
    img = Image.open(ruta_archivo)
    draw = ImageDraw.Draw(img)
    texto = f"Evidencia: {sitio} | Cliente: {identificacion_cliente} | {timestamp_legible}"
    # Fondo semi-opaco detrás del texto para que sea legible sobre cualquier fondo
    draw.rectangle([(5, 5), (5 + len(texto) * 7, 25)], fill=(255, 255, 255))
    draw.text((10, 8), texto, fill=(200, 0, 0))
    img.save(ruta_archivo)

    # Hash DESPUÉS de guardar el overlay - el hash certifica el archivo final,
    # tal como queda guardado, no la captura cruda antes de la marca visual.
    sha256 = hashlib.sha256(open(ruta_archivo, "rb").read()).hexdigest()

    return {
        "ruta": ruta_archivo,
        "timestamp": timestamp_legible,
        "sha256": sha256,
    }