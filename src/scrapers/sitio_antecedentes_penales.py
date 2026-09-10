"""
src/scrapers/sitio_antecedentes_penales.py

Certificado de Antecedentes Penales (Ministerio del Interior). Flujo de
varios pasos con hCaptcha (no reCAPTCHA), aceptación de términos, y un
asistente de 2 pantallas (cédula -> motivo de consulta -> resultado).
"""
import time

from playwright.sync_api import Page
from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, AntecedentePenal, TipoPersona
from src.documentos.evidencia import capturar_evidencia
from src.documentos.almacenamiento import guardar_pdf_local
from src.captcha.resolver import resolver_hcaptcha_con_2captcha, CaptchaResolverError
from config.settings import cargar_infra_config
from src.core.notificaciones import notificar_atencion_manual

MOTIVO_CONSULTA_DEFECTO = "Debida diligencia y cumplimiento normativo PLAFT/UAFE"

class ScraperAntecedentesPenales(BaseScraper):
    nombre_sitio = "Antecedentes Penales"
    FACTOR_VELOCIDAD = 1.0  # sin reduccion - este sitio tiene WAF (Incapsula) confirmado con evidencia real (2026-09-04); mas riesgo de bloqueo si se acelera el ritmo de interaccion

    def tiene_captcha(self, page: Page) -> bool:
        """
        Metodo requerido por el contrato de BaseScraper. OJO: se
        confirmo con evidencia real (diagnostico 2026-08-21,
        log_20260821_095119.json) que este chequeo puede devolver
        False mientras el hCaptcha esta realmente visible y
        bloqueando - el usuario resolvio un captcha real en pantalla
        durante ~17s sin que este metodo lo detectara ni una vez. Por
        eso ya NO se usa para decidir si pausar (ver
        _pagina_avanzo_de_pantalla_inicial). Se deja el metodo por
        compatibilidad con la interfaz abstracta y como dato
        informativo en logs, no como fuente de verdad.
        """
        iframe_hcaptcha = page.locator("iframe[src*='hcaptcha.com']")
        return iframe_hcaptcha.count() > 0 and iframe_hcaptcha.first.is_visible()

    def _pagina_avanzo_de_pantalla_inicial(self, page: Page) -> bool:
        """
        Senal confiable (validada con 5 corridas reales) de que ya no
        estamos atascados en la pantalla inicial: aparecio el aviso
        de cookies, el modal de terminos, o el formulario real
        (#cmbEcuatoriano). A diferencia de tiene_captcha(), esta senal
        no depende de detectar el hCaptcha en si - solo confirma que
        la pagina siguio adelante, sea porque nunca hubo captcha o
        porque ya se resolvio.
        """
        cookies = page.locator("a.cc-dismiss")
        terminos = page.locator("button:has-text('Aceptar')")
        formulario = page.locator("#cmbEcuatoriano")
        return (
            (cookies.count() > 0 and cookies.first.is_visible())
            or (terminos.count() > 0 and terminos.first.is_visible())
            or (formulario.count() > 0 and formulario.first.is_visible())
        )

    def _resolver_captcha_si_aparece(
        self,
        page: Page,
        tiempo_gracia_segundos: int = 5,
    ) -> None:
        """
        Pausa manual incondicional (fix confirmado 2026-08-21).

        Ya NO se decide si pausar en base a tiene_captcha() - ese
        chequeo tiene falsos negativos confirmados con evidencia real
        (ver docstring de tiene_captcha). En su lugar: se da un
        periodo de gracia corto para que la pagina avance por si sola
        (camino feliz, sin captcha - el caso mas comun segun las
        corridas de diagnostico). Si no avanza en ese tiempo, se
        asume INCONDICIONALMENTE - sin importar lo que diga
        tiene_captcha() - que algo requiere intervencion manual
        (tipicamente el hCaptcha) y se pausa hasta resolucion o
        timeout.
        """
        inicio = time.monotonic()
        while time.monotonic() - inicio < tiempo_gracia_segundos:
            if self._pagina_avanzo_de_pantalla_inicial(page):
                return  # camino feliz: no hizo falta intervenir
            page.wait_for_timeout(500)

        # Periodo de gracia agotado sin avance. Intento opcional con 2Captcha.
        infra = cargar_infra_config()
        if infra.captcha_enabled and infra.captcha_api_key:
            print(f"[{self.nombre_sitio}] Posible hCaptcha - intentando resolver con 2Captcha...")
            try:
                resolver_hcaptcha_con_2captcha(page, infra.captcha_api_key)
                # El callback real (onCaptchaFinished -> POST a Incapsula ->
                # recarga de pagina) puede tardar mas de 2s. Se sondea en
                # vez de chequear una sola vez con tiempo fijo - confirmado
                # que un solo chequeo a los 2s da falso negativo aunque
                # 2Captcha si resolvio correctamente (evidencia real 2026-08-24).
                resuelto = False
                for _ in range(10):
                    page.wait_for_timeout(1000)
                    if self._pagina_avanzo_de_pantalla_inicial(page):
                        resuelto = True
                        break
                if resuelto:
                    print(f"[{self.nombre_sitio}] hCaptcha resuelto automáticamente.\n")
                    return
                print(f"[{self.nombre_sitio}] 2Captcha no logró destrabar la página - cayendo a manual...\n")
            except CaptchaResolverError as e:
                print(f"[{self.nombre_sitio}] 2Captcha falló: {e} - cayendo a manual...\n")

        # Pausa manual explicita (consola)
        print(f"\n{'='*60}")
        print(f"[{self.nombre_sitio}] Posible hCaptcha detectado.")
        print(f"{'='*60}\n")
        notificar_atencion_manual("Captcha manual requerido", "Antecedentes Penales necesita que resuelvas el captcha.")
        input("Resuelve el captcha. Presiona ENTER cuando ya lo hayas resuelto...")
        print(f"[{self.nombre_sitio}] Continuando...\n")
        
    def _aceptar_terminos_si_aparece(self, page: Page) -> None:
        try:
            boton_aceptar = page.locator("button:has-text('Aceptar')")
            boton_aceptar.first.wait_for(state="visible", timeout=15000)
            # SIN force=True: el dialogo de jQuery UI necesita
            # estabilizarse (dejar de reposicionarse/animarse) antes
            # del clic real. force=True clickeaba en la coordenada
            # equivocada mientras aun se movia, reportando "exito"
            # sin que el modal se cerrara de verdad. Confirmado con
            # evidencia real (4/4 corridas limpias sin force=True:
            # logs 101001, 101301, 101343, 101417 del 2026-08-21).
            boton_aceptar.first.click(timeout=8000)
            self.delay_humano(0.5, 1.0)
            print("    [términos y condiciones] aceptados correctamente")
        except Exception as e:
            print(f"    [términos y condiciones] no apareció o no se pudo cerrar: {type(e).__name__}: {e}")

    def buscar_cliente(self, page: Page, cliente: Cliente) -> AntecedentePenal:
        """Envuelve todo el flujo con reintentos - cada reintento vuelve
        a hacer page.goto() (recarga la pagina desde cero), en vez de
        fallar directo ante un timeout puntual. Confirmado necesario
        con evidencia real: timeout en '#txtMotivo' en una corrida
        real, sitio funcionando normal en el siguiente intento."""
        return self.ejecutar_con_reintentos(self._intentar_buscar_una_vez, page, cliente)

    def _intentar_buscar_una_vez(self, page: Page, cliente: Cliente) -> AntecedentePenal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Paso 1: hCaptcha (si aparece, antes que nada más - el resto
        # de elementos no se renderiza hasta que esto se resuelva).
        # Nota: con la pausa incondicional este orden ya no es
        # necesario para la correctitud (el fix espera/pausa igual
        # sin importar el orden), pero evita que el siguiente paso
        # (cookies) pierda hasta 20s esperando un banner que todavía
        # no puede aparecer mientras el captcha bloquea la página.
        self._resolver_captcha_si_aparece(page)

        # Aviso de cookies - intento genérico con textos comunes,
        # defensivo (no falla si no aparece)
        self._cerrar_aviso_cookies_si_aparece(page)

        # Paso 2: aceptar términos y condiciones
        self._aceptar_terminos_si_aparece(page)

        # Confirmar "SI" en el combobox de ciudadano ecuatoriano (ya viene
        # por defecto, se selecciona explícito para no depender del estado).
        page.select_option("#cmbEcuatoriano", "SI")
        self.delay_humano(0.3, 0.6)

        # Paso 3-4: cédula + Siguiente
        page.fill("#txtCi", cliente.identificacion)
        self.delay_humano(0.5, 1.0)
        page.click("#btnSig1")
        self.delay_humano(1.5, 2.5)

        # Paso 5-6: motivo de consulta + Siguiente
        page.fill("#txtMotivo", MOTIVO_CONSULTA_DEFECTO)
        self.delay_humano(0.5, 1.0)
        page.click("#btnSig2")
        self.delay_humano(2.0, 3.0)

        nombre = page.locator("#dvName1").inner_text().strip()
        tipo_documento = page.locator("#dvType1").inner_text().strip()
        numero_documento = page.locator("#dvCi1").inner_text().strip()
        posee_antecedentes = page.locator("#dvAntecedent1").inner_text().strip()

        capturar_evidencia(page, cliente.identificacion_evidencia or cliente.identificacion, sitio="sitio_antecedentes_penales_resultado", carpeta_sitio="antecedentes_penales", subcarpeta=cliente.subcarpeta_evidencia)

        resultado = AntecedentePenal(
            nombre=nombre,
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            posee_antecedentes=posee_antecedentes,
        )

        # Paso 7: Visualizar Certificado (abre PDF en pestaña nueva)
        try:
            pdf_bytes = self._descargar_certificado(page)
            ruta_guardada = guardar_pdf_local(pdf_bytes, cliente.identificacion_evidencia or cliente.identificacion, "certificado_antecedentes_penales", carpeta_sitio="antecedentes_penales", subcarpeta=cliente.subcarpeta_evidencia)
            resultado.ruta_pdf = ruta_guardada
        except Exception as e:
            # Decision revertida (2026-09-09): antes, si fallaba la
            # descarga del PDF, se lanzaba una excepcion y se perdia
            # TODO el resultado (aunque nombre/posee_antecedentes ya
            # estuvieran extraidos correctamente). Ahora se devuelve el
            # resultado real igual, marcado con requiere_revision_manual
            # = True (el cliente queda en "Completado con pendientes",
            # con el SI/NO ya escrito en Excel, y "Antecedentes Penales"
            # aparece en SITIOS A REVISAR solo para ir por el PDF).
            print(f"[{self.nombre_sitio}] Falló descarga del certificado PDF: {type(e).__name__}: {e} - se conserva el resultado (SI/NO), marcado para revisión manual solo por el PDF faltante.")
            resultado.requiere_revision_manual = True

        return resultado

    def _descargar_certificado(self, page: Page) -> bytes:
        """
        Clic en "Visualizar Certificado" (abre el PDF en pestaña nueva).

        Confirmado con evidencia real (2026-09-04): el enfoque anterior
        (cerrar la pestaña y volver a pedir la misma URL por HTTP con
        page.context.request.get()) era bloqueado por Incapsula - la
        respuesta descargada era una pagina de bloqueo de Incapsula
        (958 bytes de HTML), no el PDF real. Una peticion HTTP aislada,
        aunque comparta cookies con el navegador, no tiene la misma
        huella que si paso el desafio JS de Incapsula durante la carga
        real en el navegador.

        Nuevo enfoque: se escucha (NO se intercepta - eso ya causo
        cuelgues, ver nota abajo) la respuesta de red real que carga el
        PDF en la pestaña nueva, y se toman los bytes de ESA respuesta
        (que si paso Incapsula), en vez de volver a pedirla por separado.

        NOTA HISTORICA: se probó un enfoque con page.context.route()
        (interceptar peticiones) para evitar la segunda peticion, pero
        causaba un cuelgue indefinido (sin excepcion, sin timeout)
        especificamente dentro de main.py tras pasar por varios sitios
        previos en la misma sesion de navegador - nunca reproducido en
        pruebas aisladas. route() intercepta y requiere resolver cada
        peticion manualmente; un listener de "response" (usado aqui) es
        solo observacional y no bloquea el pipeline de red, por lo que
        no debería tener el mismo riesgo de cuelgue - pero esto NO se
        ha confirmado con evidencia real todavia.
        """
        bytes_pdf_capturados = None
        respuestas_vistas_diagnostico = []  # para diagnostico si vuelve a fallar - lista de (url, content_type)

        def _capturar_respuesta_pdf(response):
            nonlocal bytes_pdf_capturados
            if bytes_pdf_capturados is not None:
                return
            content_type = response.headers.get("content-type", "")
            respuestas_vistas_diagnostico.append((response.url, content_type))
            # Criterio ampliado (2026-09-09): ademas de "pdf" en el
            # content-type o la URL, tambien se acepta
            # "application/octet-stream" (algunos servidores sirven el
            # PDF asi, sin content-type explicito de PDF) - confirmado
            # que el criterio anterior no detectaba nada en la mayoria
            # de los casos reales de esta corrida.
            es_pdf = (
                "pdf" in content_type.lower() or "pdf" in response.url.lower()
                or "octet-stream" in content_type.lower()
            )
            if not es_pdf:
                return
            try:
                # Leer los bytes AQUI, inmediatamente, dentro del propio
                # evento - confirmado con evidencia real (2026-09-09):
                # esperar a leerlos DESPUES de cerrar la pestana_pdf
                # lanzaba "TargetClosedError", porque el body() de la
                # respuesta depende de que la pagina que la origino
                # siga abierta.
                bytes_pdf_capturados = response.body()
            except Exception:
                pass  # esta respuesta en particular no se pudo leer - se sigue esperando otra

        page.context.on("response", _capturar_respuesta_pdf)
        try:
            boton_visualizar = page.locator("button:has-text('Visualizar Certificado')")

            with page.context.expect_page() as info_pestana_nueva:
                boton_visualizar.click()
            pestana_pdf = info_pestana_nueva.value

            try:
                pestana_pdf.wait_for_load_state("load", timeout=25000)
            except Exception:
                pass

            for _ in range(20):
                if bytes_pdf_capturados is not None:
                    break
                page.wait_for_timeout(500)

            if pestana_pdf and not pestana_pdf.is_closed():
                pestana_pdf.close()
        finally:
            page.context.remove_listener("response", _capturar_respuesta_pdf)

        if bytes_pdf_capturados is None:
            print(f"    [diagnóstico] Respuestas de red vistas durante la espera: {respuestas_vistas_diagnostico}")
            raise ScraperError(
                f"[{self.nombre_sitio}] No se detectó ninguna respuesta de red con contenido PDF "
                f"tras 25s + 10s de espera.",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        return bytes_pdf_capturados
    
    def _cerrar_aviso_cookies_si_aparece(self, page: Page) -> None:
        """
        Cierra el aviso de cookies, si aparece. A partir del 2do
        cliente en la misma sesion de navegador es NORMAL que este
        aviso ya no aparezca (el sitio recuerda el consentimiento via
        cookie del primer cliente) - eso no es un error. Se distingue
        explicitamente de una falla real (aparecio pero no se pudo
        cerrar) para no imprimir un warning enganoso.
        """
        boton = page.locator("a.cc-dismiss")
        try:
            boton.wait_for(state="visible", timeout=20000)
        except Exception:
            print("    [aviso cookies] no apareció (normal si ya se aceptó en esta sesión)")
            return

        try:
            page.wait_for_timeout(3000)
            boton.click(force=True, timeout=8000)
            self.delay_humano(0.5, 3.0)
            print("    [aviso cookies] cerrado correctamente")
        except Exception as e:
            print(f"    [aviso cookies] apareció pero no se pudo cerrar: {type(e).__name__}: {e}")