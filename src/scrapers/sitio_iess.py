"""
Certificado de Cumplimiento de Obligaciones Patronales (IESS).
Arquitectura JSF clásica (sin PrimeFaces). El campo de entrada NO tiene
atributo id, solo name - se usa selector de atributo.

LIMITACIÓN: para clientes Jurídica, se debe consultar con la
identificación del representante legal, no la de la empresa - misma
dependencia de la cadena de representantes que Salud (pendiente).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona

ID_CAMPO_CEDULA_RUC = 'input[name="frmCertificadoCumplimiento:j_id9"]'
ID_BOTON_CONSULTAR = 'input[name="frmCertificadoCumplimiento:j_id11"]'


class ScraperIESS(BaseScraper):
    nombre_sitio = "IESS - Certificado Cumplimiento Patronal"

    def tiene_captcha(self, page: Page) -> bool:
        # TODO: no se ha confirmado si este portal presenta captcha.
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        if cliente.tipo_persona == TipoPersona.JURIDICA:
            raise ScraperError(
                f"[{self.nombre_sitio}] Este certificado se consulta con la "
                f"identificación del representante legal, no la de la empresa "
                f"(funcionalidad de cadena de representantes pendiente).",
                resultado=ResultadoConsulta.SIN_DATOS,
            )

        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Confirmado: aunque el campo dice "Cédula / RUC", el portal
        # requiere el RUC (13 dígitos) para traer resultados correctos,
        # incluso para personas naturales - se deriva igual que en SRI
        # y Sentenciados (cédula + "001").
        ruc_a_consultar = (
            f"{cliente.identificacion}001"
            if len(cliente.identificacion.strip()) == 10
            else cliente.identificacion
        )
        page.fill(ID_CAMPO_CEDULA_RUC, ruc_a_consultar)
        self.delay_humano(0.5, 1.0)

        # Si hay registro, el envío del formulario dispara una descarga
        # directa de PDF (a diferencia de Salud, no es un blob - JSF
        # clásico normalmente devuelve el archivo con
        # Content-Disposition: attachment, capturable con el evento
        # nativo de descarga de Playwright).
        pdf_bytes = None
        hay_registro = False
        mensaje_error = ""
        try:
            with page.expect_download(timeout=10000) as info_descarga:
                page.click(ID_BOTON_CONSULTAR)
            descarga = info_descarga.value
            with open(descarga.path(), "rb") as f:
                pdf_bytes = f.read()
            hay_registro = True
        except Exception:
            # No hubo descarga - el portal responde con un mensaje
            # explícito ("El RUC ingresado no es correcto") en vez de
            # un mensaje de "sin registros".
            # Esto es un resultado legítimo (la persona no tiene RUC de
            # empleador válido en el IESS), no necesariamente un error
            # técnico del scraper.
            self.delay_humano(1.5, 2.5)
            try:
                texto_pagina = page.locator("#formContenido\\:mensajePrincipal").inner_text()
                mensaje_error = texto_pagina.strip()
            except Exception:
                mensaje_error = "Mensaje de error no capturado"

        resultado = {"hay_registro": hay_registro, "ruta_pdf": "", "iess": mensaje_error, "deuda_obligaciones": ""}
        if pdf_bytes is not None:
            from src.documentos.almacenamiento import guardar_pdf_local
            ruta_guardada = guardar_pdf_local(pdf_bytes, cliente.identificacion, "certificado_iess", carpeta_sitio="iess")
            resultado["ruta_pdf"] = ruta_guardada

            try:
                texto_iess, valor_deuda = self._extraer_mora_del_pdf(pdf_bytes)
                resultado["iess"] = texto_iess
                resultado["deuda_obligaciones"] = valor_deuda
            except Exception as e:
                print(f"[{cliente.identificacion}] Falló extracción de mora del PDF: {e}")

        return resultado

    def _extraer_mora_del_pdf(self, pdf_bytes: bytes) -> tuple[str, str]:
        """
        Extrae el texto de la columna "IESS" (SI/NO registra obligaciones
        patronales en mora, tal cual aparece en el certificado) y el
        valor de la deuda por separado. Certificado de texto libre, no
        tabla - se usa regex sobre la frase confirmada con un caso real.
        """
        import re
        from src.procesamiento.resumen_ia import extraer_texto_pdf

        texto = extraer_texto_pdf(pdf_bytes)
        texto_normalizado = " ".join(texto.split())  # colapsa saltos de línea/espacios múltiples

        coincidencia = re.search(
            r"((?:SI|NO)\s+registra\s+obligaciones\s+patronales\s+en\s+mora)"
            r"(?:\s+por\s+un\s+valor\s+de\s+USD\s+([\d.,]+))?",
            texto_normalizado,
            re.IGNORECASE,
        )

        if not coincidencia:
            return "", ""

        texto_iess = coincidencia.group(1).strip()
        valor_deuda = coincidencia.group(2) or ""
        return texto_iess, valor_deuda