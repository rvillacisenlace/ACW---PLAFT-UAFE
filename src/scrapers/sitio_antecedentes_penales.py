"""
src/scrapers/sitio_antecedentes_penales.py

Certificado de Antecedentes Penales (Ministerio del Interior). Flujo de
varios pasos con hCaptcha (no reCAPTCHA), aceptación de términos, y un
asistente de 2 pantallas (cédula -> motivo de consulta -> resultado).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, AntecedentePenal, TipoPersona
from src.documentos.evidencia import capturar_evidencia
from src.documentos.almacenamiento import guardar_pdf_local
from src.captcha.resolver import resolver_hcaptcha_con_2captcha, CaptchaResolverError
from config.settings import cargar_infra_config

MOTIVO_CONSULTA_DEFECTO = "Debida diligencia y cumplimiento normativo PLAFT/UAFE"


class ScraperAntecedentesPenales(BaseScraper):
    nombre_sitio = "Antecedentes Penales"

    def tiene_captcha(self, page: Page) -> bool:
        iframe_hcaptcha = page.locator("iframe[src*='hcaptcha.com']")
        return iframe_hcaptcha.count() > 0 and iframe_hcaptcha.first.is_visible()

    def _resolver_captcha_si_aparece(self, page: Page, tiempo_espera_segundos: int = 120) -> None:
        """
        El hCaptcha no siempre aparece. Si aparece, se intenta resolver
        automáticamente con 2Captcha; si falla, se cae a pausa manual.
        """
        if not self.tiene_captcha(page):
            return

        infra = cargar_infra_config()
        if infra.captcha_api_key:
            print(f"[{self.nombre_sitio}] hCaptcha detectado - intentando resolver con 2Captcha...")
            try:
                resolver_hcaptcha_con_2captcha(page, infra.captcha_api_key)
                page.wait_for_timeout(2000)
                if not self.tiene_captcha(page):
                    print(f"[{self.nombre_sitio}] hCaptcha resuelto automáticamente.\n")
                    return
                print(f"[{self.nombre_sitio}] 2Captcha no logró pasar la validación - cayendo a manual...\n")
            except CaptchaResolverError as e:
                print(f"[{self.nombre_sitio}] 2Captcha falló: {e} - cayendo a manual...\n")

        print(f"\n{'='*60}")
        print("HCAPTCHA DETECTADO - Se requiere intervención manual")
        print(f"Resuelve el captcha en la ventana del navegador ahora.")
        print(f"{'='*60}\n")

        intervalos = tiempo_espera_segundos // 3
        for _ in range(intervalos):
            page.wait_for_timeout(3000)
            if not self.tiene_captcha(page):
                print("Captcha resuelto - continuando automáticamente.\n")
                return

        raise ScraperError(
            f"[{self.nombre_sitio}] hCaptcha sin resolución dentro del tiempo límite.",
            resultado=ResultadoConsulta.ERROR_CAPTCHA,
        )

    def _aceptar_terminos_si_aparece(self, page: Page) -> None:
        try:
            boton_aceptar = page.locator("button:has-text('Aceptar')")
            boton_aceptar.first.wait_for(state="visible", timeout=15000)
            boton_aceptar.first.click(force=True, timeout=8000)
            self.delay_humano(0.5, 1.0)
            print("    [términos y condiciones] aceptados correctamente")
        except Exception as e:
            print(f"    [términos y condiciones] no apareció o no se pudo cerrar: {type(e).__name__}: {e}")

    def buscar_cliente(self, page: Page, cliente: Cliente) -> AntecedentePenal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Aviso de cookies (aparece antes que el resto) - intento
        # genérico con textos comunes, defensivo (no falla si no aparece)
        self._cerrar_aviso_cookies_si_aparece(page)

        # Paso 1: hCaptcha (si aparece, antes que nada más)
        self._resolver_captcha_si_aparece(page)

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

        capturar_evidencia(page, cliente.identificacion, sitio="sitio_antecedentes_penales_resultado")

        resultado = AntecedentePenal(
            nombre=nombre,
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            posee_antecedentes=posee_antecedentes,
        )

        # Paso 7: Visualizar Certificado (abre PDF en pestaña nueva)
        try:
            pdf_bytes = self._descargar_certificado(page)
            ruta_guardada = guardar_pdf_local(pdf_bytes, cliente.identificacion, "certificado_antecedentes_penales")
            resultado.ruta_pdf = ruta_guardada
        except Exception as e:
            print(f"[{cliente.identificacion}] Falló descarga del certificado: {type(e).__name__}: {e}")

        return resultado

    def _descargar_certificado(self, page: Page) -> bytes:
        """
        Clic en "Visualizar Certificado" (abre el PDF en pestaña nueva,
        renderizado en el visor nativo de Chrome). Los datos de esa
        respuesta NO son legibles vía response.body() de Playwright
        cuando el PDF se renderiza inline (limitación conocida de
        Playwright/CDP) - en vez de interceptar la respuesta del
        navegador, se vuelve a pedir la misma URL directamente por HTTP
        usando el contexto (comparte cookies/sesión), lo que sí es
        confiable porque no pasa por el visor de PDF.
        """
        boton_visualizar = page.locator("button:has-text('Visualizar Certificado')")

        with page.context.expect_page() as info_pestana_nueva:
            boton_visualizar.click()
        pestana_pdf = info_pestana_nueva.value

        pestana_pdf.wait_for_load_state("domcontentloaded", timeout=15000)
        url_pdf = pestana_pdf.url

        if pestana_pdf and not pestana_pdf.is_closed():
            pestana_pdf.close()

        if not url_pdf or "pdf" not in url_pdf.lower() and "certificado" not in url_pdf.lower():
            # La URL no parece ser directamente el PDF - de todas formas
            # intentamos la petición, pero lo anotamos por si falla.
            print(f"    [aviso] URL de la pestaña no contiene 'pdf' explícito: {url_pdf}")

        respuesta = page.context.request.get(url_pdf)
        if not respuesta.ok:
            raise ScraperError(
                f"[{self.nombre_sitio}] Falló la re-descarga directa del certificado "
                f"(status {respuesta.status}) desde {url_pdf}",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        return respuesta.body()

    def _cerrar_aviso_cookies_si_aparece(self, page: Page) -> None:
        """
        Cierra el aviso de cookies (librería "cookieconsent"). Usa
        force=True porque el banner suele tener una animación de entrada
        que puede interferir con la verificación de "clickeable" normal
        de Playwright.
        """
        try:
            boton = page.locator("a.cc-dismiss")
            boton.wait_for(state="visible", timeout=20000)
            boton.click(force=True, timeout=8000)
            self.delay_humano(0.5, 1.0)
            print("    [aviso cookies] cerrado correctamente")
        except Exception as e:
            print(f"    [aviso cookies] no se pudo cerrar automáticamente: {type(e).__name__}: {e}")