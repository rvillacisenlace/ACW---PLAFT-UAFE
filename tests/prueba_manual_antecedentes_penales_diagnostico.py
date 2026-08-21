"""
tests/prueba_manual_antecedentes_penales_diagnostico.py  (v2)

Correccion sobre la v1: la v1 asumia el mismo orden fijo que el
codigo de produccion (cookies -> captcha -> terminos), y por eso no
llegaba a correr bien - exactamente el mismo defecto que se queria
diagnosticar.

Esta version NO asume ningun orden. Corre un loop de polling que en
cada iteracion revisa el estado de los 3 elementos (hCaptcha, aviso
de cookies, terminos y condiciones) y reacciona a lo que sea que
aparezca, en el orden en que aparezca. Asi:
1. Obtenemos evidencia real de que orden(es) ocurre(n) en la practica
   (para eso es el log).
2. El propio script queda utilizable para correr el flujo completo
   sin importar el orden, que es el comportamiento que finalmente
   necesita el scraper de produccion.

Sigue sin usar ScraperAntecedentesPenales directamente (para poder
instrumentar), asi que sigue siendo diagnostico, no un reemplazo del
test de integracion.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

URL_ANTECEDENTES_PENALES = "https://certificados.ministeriodelinterior.gob.ec/gestorcertificados/antecedentes/"
CARPETA_DIAGNOSTICO = Path("tests/diagnostico_antecedentes_penales")
CARPETA_DIAGNOSTICO.mkdir(parents=True, exist_ok=True)

eventos = []
t0 = time.monotonic()


def log_evento(tipo: str, detalle: dict):
    evento = {
        "t_relativo_seg": round(time.monotonic() - t0, 2),
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "tipo": tipo,
        **detalle,
    }
    eventos.append(evento)
    print(f"[t={evento['t_relativo_seg']:>6.2f}s] {tipo}: {detalle}")


def snapshot(page: Page, etiqueta: str):
    ruta = CARPETA_DIAGNOSTICO / f"{etiqueta}_{int(time.time()*1000)}.png"
    try:
        page.screenshot(path=str(ruta))
    except Exception as e:
        ruta = f"ERROR: {e}"
    log_evento("snapshot", {"etiqueta": etiqueta, "screenshot": str(ruta)})


def hcaptcha_visible(page: Page) -> bool:
    loc = page.locator("iframe[src*='hcaptcha.com']")
    return loc.count() > 0 and loc.first.is_visible()


def inventario_iframes_hcaptcha(page: Page) -> list[dict]:
    """
    A diferencia de hcaptcha_visible() (que replica el bug de
    produccion al usar .first), esto revisa TODOS los iframes que
    matchean 'hcaptcha.com' e individualmente su src y visibilidad.
    Objetivo: confirmar si hay mas de un iframe matcheando y si
    '.first' esta agarrando el que no corresponde.
    """
    loc = page.locator("iframe[src*='hcaptcha.com']")
    total = loc.count()
    detalle = []
    for i in range(total):
        item = loc.nth(i)
        try:
            detalle.append({
                "indice": i,
                "src": item.get_attribute("src"),
                "visible": item.is_visible(),
            })
        except Exception as e:
            detalle.append({"indice": i, "error": str(e)})
    return {"total_matches": total, "iframes": detalle}


def cookies_visible(page: Page) -> bool:
    loc = page.locator("a.cc-dismiss")
    return loc.count() > 0 and loc.first.is_visible()


def terminos_visible(page: Page) -> bool:
    loc = page.locator("button:has-text('Aceptar')")
    return loc.count() > 0 and loc.first.is_visible()


def formulario_listo(page: Page) -> bool:
    # Senal de que ya pasamos captcha + cookies + terminos: el combobox
    # de ciudadano ecuatoriano del formulario real esta visible.
    loc = page.locator("#cmbEcuatoriano")
    return loc.count() > 0 and loc.first.is_visible()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    page.goto(URL_ANTECEDENTES_PENALES)
    log_evento("navegacion", {"url": URL_ANTECEDENTES_PENALES})
    snapshot(page, "00_carga_inicial")

    estado_previo = {"hcaptcha": None, "cookies": None, "terminos": None}
    cookies_ya_cerradas = False
    terminos_ya_aceptados = False

    print(
        "\nEl script va a monitorear la pagina y reaccionar a lo que "
        "aparezca (captcha, cookies o terminos), sin importar el "
        "orden. Si aparece el captcha, RESUELVELO TU manualmente en "
        "la ventana del navegador cuando lo veas - el script solo "
        "espera a que desaparezca.\n"
    )

    TIEMPO_MAXIMO_SEG = 180
    VENTANA_SONDEO_FINO_SEG = 40  # primeros 40s: inventario completo cada 0.5s
    inicio_loop = time.monotonic()
    ultimo_inventario = None

    while time.monotonic() - inicio_loop < TIEMPO_MAXIMO_SEG:
        t_transcurrido = time.monotonic() - inicio_loop

        estado_actual = {
            "hcaptcha": hcaptcha_visible(page),
            "cookies": cookies_visible(page),
            "terminos": terminos_visible(page),
        }

        # Loguear SOLO cuando cambia el estado de algo (evita ruido)
        for clave, valor in estado_actual.items():
            if valor != estado_previo[clave]:
                log_evento("cambio_estado", {"elemento": clave, "visible": valor})
                snapshot(page, f"cambio_{clave}_{valor}")
        estado_previo = estado_actual

        # Durante la ventana inicial, ademas del estado agregado
        # (que replica el bug de .first), logueamos el inventario
        # COMPLETO de iframes hcaptcha para ver si hay mas de uno y
        # cual esta realmente visible.
        if t_transcurrido < VENTANA_SONDEO_FINO_SEG:
            inv = inventario_iframes_hcaptcha(page)
            if inv != ultimo_inventario:
                log_evento("inventario_iframes_hcaptcha", inv)
                ultimo_inventario = inv

        # Reaccionar a cookies (con la espera de 3s que describiste)
        if estado_actual["cookies"] and not cookies_ya_cerradas:
            log_evento("accion", {"elemento": "cookies", "accion": "esperando 3s antes de clic"})
            page.wait_for_timeout(3000)
            try:
                page.locator("a.cc-dismiss").first.click(force=True, timeout=8000)
                cookies_ya_cerradas = True
                log_evento("accion", {"elemento": "cookies", "accion": "clic Aceptar exitoso"})
            except Exception as e:
                log_evento("accion", {"elemento": "cookies", "accion": "clic fallo", "error": str(e)})

        # Reaccionar a terminos (boton "Aceptar" del modal de T&C -
        # OJO: NO confundir con el boton de cookies, por eso solo se
        # intenta cuando cookies ya no esta bloqueando o ya se cerro)
        if estado_actual["terminos"] and not terminos_ya_aceptados and cookies_ya_cerradas:
            boton = page.locator("button:has-text('Aceptar')").first
            try:
                estado_boton = {
                    "disabled_attr": boton.get_attribute("disabled"),
                    "aria_disabled": boton.get_attribute("aria-disabled"),
                    "class": boton.get_attribute("class"),
                }
                log_evento("estado_boton_terminos_antes_de_clic", estado_boton)
            except Exception as e:
                log_evento("estado_boton_terminos_antes_de_clic", {"error": str(e)})

            try:
                # SIN force=True a proposito: si el boton no esta
                # realmente accionable (deshabilitado, tapado, etc.),
                # queremos que Playwright lo diga con un error claro,
                # no que el clic "tenga exito" silenciosamente sobre
                # un boton que en realidad ignoro el evento.
                boton.click(timeout=8000)
                terminos_ya_aceptados = True
                log_evento("accion", {"elemento": "terminos", "accion": "clic Aceptar exitoso (sin force)"})
            except Exception as e:
                log_evento("accion", {"elemento": "terminos", "accion": "clic fallo (sin force)", "error": f"{type(e).__name__}: {e}"})

        # Captcha: NO se auto-resuelve, solo se loguea y se deja que
        # el usuario lo resuelva manualmente en la ventana.

        if formulario_listo(page):
            log_evento("formulario_listo", {"cookies_cerradas": cookies_ya_cerradas, "terminos_aceptados": terminos_ya_aceptados})
            snapshot(page, "99_formulario_listo")
            break

        time.sleep(0.5 if t_transcurrido < VENTANA_SONDEO_FINO_SEG else 1)
    else:
        log_evento("timeout", {"segundos": TIEMPO_MAXIMO_SEG, "formulario_listo": False})

    ruta_log = CARPETA_DIAGNOSTICO / f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    ruta_log.write_text(json.dumps(eventos, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nLog guardado en: {ruta_log}")

    input("\nPresiona ENTER para cerrar el navegador...")
    browser.close()