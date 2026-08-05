"""
Resuelve reCAPTCHA v2 (tipo checkbox, confirmado que es el único tipo
visto en Función Judicial) usando el servicio 2Captcha. Requiere
CAPTCHA_API_KEY configurada en .env - mientras no esté disponible, el
llamador debe usar la pausa manual como respaldo (ver
_resolver_captcha_manual en sitio1_funcion_judicial.py).
"""
from twocaptcha import TwoCaptcha
from playwright.sync_api import Page


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

    return True