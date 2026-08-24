"""
Resuelve reCAPTCHA v2 (tipo checkbox, confirmado que es el único tipo
visto en Función Judicial) usando el servicio 2Captcha. Requiere
CAPTCHA_API_KEY configurada en .env - mientras no esté disponible, el
llamador debe usar la pausa manual como respaldo (ver
_resolver_captcha_manual en sitio1_funcion_judicial.py).
"""
from twocaptcha import TwoCaptcha
from playwright.sync_api import Page

import truststore
truststore.inject_into_ssl()

class CaptchaResolverError(Exception):
    """Error específico al intentar resolver el captcha vía 2Captcha."""
    pass


def resolver_con_2captcha(page: Page, api_key: str, tiempo_espera_segundos: int = 120) -> bool:
    """
    Intenta resolver un reCAPTCHA v2 visible en la página actual usando
    2Captcha. Devuelve True si se resolvió e inyectó el token
    correctamente, False si falló (el llamador debe entonces caer en
    resolución manual como respaldo).
    """
    if not api_key:
        raise CaptchaResolverError("CAPTCHA_API_KEY no está configurada en .env")

    # El timeout se configura en el constructor (defaultTimeout), NO como
    # argumento de .recaptcha() - pasarlo ahí causaba un conflicto interno
    # ("multiple values for keyword argument 'timeout'") con la librería.
    solver = TwoCaptcha(api_key, defaultTimeout=tiempo_espera_segundos, pollingInterval=10)

    # Extraer el site_key del iframe de reCAPTCHA presente en la página
    iframe_recaptcha = page.locator("iframe[src*='recaptcha']").first
    if iframe_recaptcha.count() == 0:
        raise CaptchaResolverError("No se encontró el iframe de reCAPTCHA en la página")

    src_iframe = iframe_recaptcha.get_attribute("src") or ""
    site_key = None
    for parte in src_iframe.split("&"):
        if parte.startswith("k="):
            site_key = parte.split("=", 1)[1]
            break
        if "k=" in parte:
            site_key = parte.split("k=")[-1].split("&")[0]
            break

    if not site_key:
        raise CaptchaResolverError(
            f"No se pudo extraer el site_key del iframe de reCAPTCHA (src: {src_iframe[:200]})"
        )

    try:
        resultado = solver.recaptcha(
            sitekey=site_key,
            url=page.url,
        )
        token = resultado["code"]
    except Exception as e:
        raise CaptchaResolverError(f"2Captcha no pudo resolver el desafío: {e}")

    # Inyectar el token resuelto en el campo oculto que reCAPTCHA espera,
    # y disparar el callback de validación si existe.
    page.evaluate(
        """(token) => {
            const campo = document.getElementById('g-recaptcha-response');
            if (campo) { campo.innerHTML = token; campo.value = token; }
            if (typeof ___grecaptcha_cfg !== 'undefined') {
                Object.values(___grecaptcha_cfg.clients).forEach((cliente) => {
                    const cb = cliente?.O?.callback || cliente?.l?.callback;
                    if (cb) cb(token);
                });
            }
        }""",
        token,
    )

    page.wait_for_timeout(2000)

    # El portal (PrimeFaces) requiere este clic EXPLÍCITO en "Verificar"
    # para enviar el token resuelto al servidor - un humano lo hace por
    # instinto tras marcar el checkbox, pero el flujo automático nunca lo
    # hacía, dejando el token inyectado sin someterse nunca a validación.
    boton_verificar = page.locator("button:has-text('Verificar')")
    if boton_verificar.count() > 0 and boton_verificar.first.is_visible():
        boton_verificar.first.click()
        page.wait_for_timeout(2500)

def resolver_hcaptcha_con_2captcha(page: Page, api_key: str, tiempo_espera_segundos: int = 180) -> bool:
    """
    Resuelve hCaptcha con 2Captcha. El sitio esta protegido por
    Imperva Incapsula: cuando el WAF activa el desafio, el hCaptcha
    completo (widget + textareas + callback JS) vive DENTRO de un
    iframe anidado (src contiene "_Incapsula_Resource"), no en el
    documento principal. Se busca ese frame primero; si no existe,
    se usa la pagina principal como respaldo. Confirmado 2026-08-21.
    """
    if not api_key:
        raise CaptchaResolverError("CAPTCHA_API_KEY no está configurada en .env")

    solver = TwoCaptcha(api_key, defaultTimeout=tiempo_espera_segundos, pollingInterval=10)

    frame = next((f for f in page.frames if "_Incapsula_Resource" in f.url), page.main_frame)

    widget = frame.locator(".h-captcha[data-sitekey]").first
    if widget.count() == 0:
        raise CaptchaResolverError("No se encontró el widget de hCaptcha (data-sitekey)")

    site_key = widget.get_attribute("data-sitekey")
    if not site_key:
        raise CaptchaResolverError("El widget de hCaptcha no tiene data-sitekey")

    try:
        resultado = solver.hcaptcha(sitekey=site_key, url=page.url)
        token = resultado["code"]
    except Exception as e:
        raise CaptchaResolverError(f"2Captcha no pudo resolver el hCaptcha: {e}")

    # Se invoca onCaptchaFinished directamente (el callback real del
    # sitio, definido en ese mismo frame) en vez de solo rellenar
    # textareas - hace el POST a Incapsula y recarga la pagina, igual
    # que si el usuario lo hubiera resuelto a mano.
    frame.evaluate(
        """(token) => {
            if (typeof onCaptchaFinished === 'function') {
                onCaptchaFinished(token);
            } else {
                document.querySelectorAll(
                    'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]'
                ).forEach(c => { c.innerHTML = token; c.value = token; });
            }
        }""",
        token,
    )

def resolver_captcha_imagen_con_2captcha(
    page: Page,
    api_key: str,
    selector_imagen: str,
    selector_campo_respuesta: str,
    tiempo_espera_segundos: int = 120,
) -> bool:
    """
    Resuelve un captcha de imagen clasico (texto distorsionado) con el
    metodo "normal" de 2Captcha. La imagen debe venir embebida como
    base64 en el atributo src de un <img> (data:image/...;base64,...).
    Generico via selectores - reutilizable en otros sitios con el
    mismo patron (ej. Contraloria).
    """
    if not api_key:
        raise CaptchaResolverError("CAPTCHA_API_KEY no está configurada en .env")

    import base64

    imagen = page.locator(selector_imagen)
    if imagen.count() == 0:
        raise CaptchaResolverError(f"No se encontró la imagen del captcha ({selector_imagen})")

    # Screenshot del elemento en vez de leer el atributo src - funciona
    # igual si la imagen viene embebida en base64 (Contraloria) o
    # generada dinamicamente por el servidor via URL (Quito/Telerik).
    try:
        bytes_imagen = imagen.first.screenshot()
    except Exception as e:
        raise CaptchaResolverError(f"No se pudo capturar la imagen del captcha: {e}")

    datos_base64 = base64.b64encode(bytes_imagen).decode("ascii")

    solver = TwoCaptcha(api_key, defaultTimeout=tiempo_espera_segundos, pollingInterval=5)
    try:
        resultado = solver.normal(datos_base64)
        codigo = resultado["code"]
    except Exception as e:
        raise CaptchaResolverError(f"2Captcha no pudo resolver el captcha de imagen: {e}")

    page.fill(selector_campo_respuesta, codigo)
    return True