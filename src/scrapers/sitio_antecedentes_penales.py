"""
Certificado de Antecedentes Penales (Ministerio del Interior).
Asistente de 3 pasos: cédula -> motivo de consulta -> resultado.
Solo requiere captura de evidencia (screenshot), sin descarga de PDF/certificado.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta
from src.documentos.evidencia import capturar_evidencia

MOTIVO_CONSULTA_DEFECTO = "Debida diligencia y cumplimiento normativo PLAFT/UAFE"


class ScraperAntecedentesPenales(BaseScraper):
    nombre_sitio = "Antecedentes Penales"

    def tiene_captcha(self, page: Page) -> bool:
        # TODO: no se detectó captcha en el HTML inspeccionado - verificar
        # con uso real, dado que otros portales del Ministerio del
        # Interior sí suelen tenerlo.
        return False

    def _aceptar_terminos_si_aparece(self, page: Page) -> None:
        """
        El portal puede mostrar un modal de Términos y Condiciones al
        cargar. Se maneja de forma defensiva: si aparece, se acepta;
        si no, se continúa sin error.
        """
        try:
            boton_aceptar = page.locator("button:has-text('Aceptar')")
            boton_aceptar.first.wait_for(state="visible", timeout=5000)
            boton_aceptar.first.click()
            self.delay_humano(0.5, 1.0)
        except Exception:
            pass  # el modal no apareció - continuar normal

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        self._aceptar_terminos_si_aparece(page)

        # Paso 1: cédula
        page.fill("#txtCi", cliente.identificacion)
        self.delay_humano(0.5, 1.0)
        page.click("#btnSig1")
        self.delay_humano(1.5, 2.5)

        # Paso 2: motivo de consulta (mínimo 10 caracteres, según el
        # propio portal en sus preguntas frecuentes)
        page.fill("#txtMotivo", MOTIVO_CONSULTA_DEFECTO)
        self.delay_humano(0.5, 1.0)
        page.click("#btnSig2")
        self.delay_humano(2.0, 3.0)

        # Paso 3: resultado
        nombre = page.locator("#dvName1").inner_text().strip()
        tipo_documento = page.locator("#dvType1").inner_text().strip()
        numero_documento = page.locator("#dvCi1").inner_text().strip()
        posee_antecedentes = page.locator("#dvAntecedent1").inner_text().strip()

        capturar_evidencia(
            page, cliente.identificacion,
            sitio="sitio_antecedentes_penales"
        )

        return {
            "nombre": nombre,
            "tipo_documento": tipo_documento,
            "numero_documento": numero_documento,
            "posee_antecedentes": posee_antecedentes,
        }