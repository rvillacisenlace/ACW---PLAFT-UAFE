import hashlib
import os
from datetime import datetime
from playwright.sync_api import Page
from PIL import Image, ImageDraw


def capturar_evidencia(
    page: Page, identificacion_cliente: str, sitio: str, carpeta_sitio: str,
    base_dir: str = "./data/staging", pagina_completa: bool = True
) -> dict:
    """
    Captura screenshot de la página actual, agrega overlay de fecha/hora,
    y calcula hash SHA-256.

    carpeta_sitio: nombre corto del sitio (ej. "sri", "scvs",
    "contraloria") - organiza la evidencia en una subcarpeta dentro de
    la carpeta del cliente, para no mezclar archivos de los 8 sitios
    juntos en un solo directorio plano.

    pagina_completa=False: usa captura de solo el viewport visible (ver
    nota histórica: necesario para visores de PDF embebidos).
    """
    ahora = datetime.now()
    carpeta = os.path.join(
        base_dir, "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}",
        identificacion_cliente, carpeta_sitio
    )
    os.makedirs(carpeta, exist_ok=True)

    timestamp_archivo = ahora.strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"evidencia_{sitio}_{timestamp_archivo}.png"
    ruta_archivo = os.path.join(carpeta, nombre_archivo)

    # Forzar scroll al inicio absoluto antes de capturar - hipótesis:
    # la inconsistencia de la barra fija superpuesta (a veces arriba,
    # a veces a mitad de la captura) puede deberse a que el navegador
    # no siempre empieza el proceso de captura por segmentos desde el
    # mismo punto de scroll.
    if pagina_completa:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)

    page.screenshot(path=ruta_archivo, full_page=pagina_completa)

    timestamp_legible = ahora.strftime("%Y-%m-%d %H:%M:%S")
    img = Image.open(ruta_archivo)
    draw = ImageDraw.Draw(img)
    texto = f"Evidencia: {sitio} | Cliente: {identificacion_cliente} | {timestamp_legible}"
    draw.rectangle([(5, 5), (5 + len(texto) * 7, 25)], fill=(255, 255, 255))
    draw.text((10, 8), texto, fill=(200, 0, 0))
    img.save(ruta_archivo)

    sha256 = hashlib.sha256(open(ruta_archivo, "rb").read()).hexdigest()

    return {
        "ruta": ruta_archivo,
        "timestamp": timestamp_legible,
        "sha256": sha256,
    }