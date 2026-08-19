"""
SERCOP - Certificados de cumplimiento. Cada cliente requiere AMBOS
certificados:
- 6903: No tener procesos adjudicados o contratos pendientes con el Estado
- 6902: No ser contratista incumplido o adjudicatario fallido con el Estado

Para Jurídica, requiere también la identificación del representante
legal (ya resuelta vía la cadena de SRI).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona
from src.documentos.evidencia import capturar_evidencia

TIPO_CERTIFICADO_SIN_CONTRATOS_PENDIENTES = "6903"
TIPO_CERTIFICADO_SIN_INCUMPLIMIENTOS = "6902"
TIPO_PERSONA_JURIDICA = "6900"
TIPO_PERSONA_NATURAL = "6901"


class ScraperSERCOPCertificados(BaseScraper):
    nombre_sitio = "SERCOP - Certificados"

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente, ruc_representante_legal: str = "") -> dict:
        """
        Consulta AMBOS certificados para el cliente. Devuelve un
        diccionario con el resultado de cada uno.
        """
        if cliente.tipo_persona == TipoPersona.JURIDICA and not ruc_representante_legal:
            raise ScraperError(
                f"[{self.nombre_sitio}] Cliente Jurídica requiere la identificación del "
                f"representante legal, no proporcionada.",
                resultado=ResultadoConsulta.SIN_DATOS,
            )

        resultado_contratos_pendientes = self._consultar_certificado(
            page, cliente, ruc_representante_legal, TIPO_CERTIFICADO_SIN_CONTRATOS_PENDIENTES
        )
        resultado_incumplimientos = self._consultar_certificado(
            page, cliente, ruc_representante_legal, TIPO_CERTIFICADO_SIN_INCUMPLIMIENTOS
        )

        return {
            "contratos_pendientes": resultado_contratos_pendientes,
            "incumplimientos": resultado_incumplimientos,
        }

    def _consultar_certificado(self, page: Page, cliente: Cliente, ruc_representante_legal: str, tipo_certificado: str) -> dict:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        self._aceptar_cookies_si_aparece(page)

        page.select_option("#cmbTipoCertificado", tipo_certificado)
        self.delay_humano(0.5, 1.0)

        tipo_persona_valor = (
            TIPO_PERSONA_JURIDICA if cliente.tipo_persona == TipoPersona.JURIDICA
            else TIPO_PERSONA_NATURAL
        )
        page.select_option("#cmbTipoPersona", tipo_persona_valor)
        self.delay_humano(0.5, 1.0)

        ruc_a_consultar = (
            cliente.identificacion if len(cliente.identificacion.strip()) == 13
            else f"{cliente.identificacion}001"
        )
        page.fill("#ruc", ruc_a_consultar)
        self.delay_humano(0.5, 1.0)

        if cliente.tipo_persona == TipoPersona.JURIDICA:
            # Prioridad: primero cédula (10 dígitos) del representante
            # legal; si SERCOP dice que no coincide con el RUC de la
            # empresa según datos del SRI, se reintenta con el RUC
            # derivado (+001) como respaldo.
            cedula_representante = (
                ruc_representante_legal[:10] if len(ruc_representante_legal.strip()) == 13
                else ruc_representante_legal
            )
            page.fill("#rucRepre", cedula_representante)
            self.delay_humano(0.5, 1.0)

        page.click("button:has-text('Buscar')")

        try:
            page.wait_for_function(
                """() => {
                    const texto = document.body.innerText;
                    return texto.includes('ALERTA') || texto.includes('Emitir Certificado') ||
                           texto.includes('no está asociada con el RUC ingresado');
                }""",
                timeout=15000,
            )
        except Exception:
            print(f"    [{self.nombre_sitio}] Advertencia: no se confirmó ningún resultado tras 15s (tipo {tipo_certificado}).")

        self.delay_humano(1.0, 1.5)

        # Reintento con RUC derivado si la cédula del representante no
        # coincidió según SERCOP/SRI.
        if cliente.tipo_persona == TipoPersona.JURIDICA and "no está asociada con el RUC ingresado" in page.content():
            ruc_derivado_representante = (
                ruc_representante_legal if len(ruc_representante_legal.strip()) == 13
                else f"{ruc_representante_legal}001"
            )
            print(f"    [{self.nombre_sitio}] Cédula del representante no coincidió - reintentando con RUC derivado...")

            page.goto(self.url_base)
            self.delay_humano(1.5, 2.5)
            self._aceptar_cookies_si_aparece(page)

            page.select_option("#cmbTipoCertificado", tipo_certificado)
            self.delay_humano(0.5, 1.0)
            page.select_option("#cmbTipoPersona", TIPO_PERSONA_JURIDICA)
            self.delay_humano(0.5, 1.0)

            ruc_empresa = (
                cliente.identificacion if len(cliente.identificacion.strip()) == 13
                else f"{cliente.identificacion}001"
            )
            page.fill("#ruc", ruc_empresa)
            self.delay_humano(0.5, 1.0)
            page.fill("#rucRepre", ruc_derivado_representante)
            self.delay_humano(0.5, 1.0)

            page.click("button:has-text('Buscar')")
            try:
                page.wait_for_function(
                    """() => {
                        const texto = document.body.innerText;
                        return texto.includes('ALERTA') || texto.includes('Emitir Certificado');
                    }""",
                    timeout=15000,
                )
            except Exception:
                print(f"    [{self.nombre_sitio}] Advertencia: reintento con RUC derivado tampoco confirmó resultado tras 15s.")
            self.delay_humano(1.0, 1.5)

        return self._extraer_resultado(page, cliente, tipo_certificado)

    def _aceptar_cookies_si_aparece(self, page: Page) -> None:
        try:
            boton = page.locator("button.cc-dismiss")
            boton.wait_for(state="visible", timeout=5000)
            boton.click()
            self.delay_humano(0.5, 1.0)
        except Exception:
            pass

    def _extraer_resultado(self, page: Page, cliente: Cliente, tipo_certificado: str) -> dict:
        capturar_evidencia(
            page, cliente.identificacion,
            sitio=f"sitio_sercop_certificado_{tipo_certificado}_resultado",
            carpeta_sitio="sercop"
        )

        contenido_pagina = page.content()

        if "¡ALERTA!" in contenido_pagina:
            return {"tiene_alerta": True, "resultado": "SI", "ruta_pdf": "", "mensaje_certificado": ""}

        if "Emitir Certificado" in contenido_pagina:
            try:
                pdf_bytes, mensaje_certificado = self._descargar_certificado(page, cliente, tipo_certificado)
                from src.documentos.almacenamiento import guardar_pdf_local
                ruta_pdf = guardar_pdf_local(pdf_bytes, cliente.identificacion, f"certificado_sercop_{tipo_certificado}", carpeta_sitio="sercop")
                return {"tiene_alerta": False, "resultado": "NO", "ruta_pdf": ruta_pdf, "mensaje_certificado": mensaje_certificado}
            except Exception as e:
                print(f"[{cliente.identificacion}] Falló descarga del certificado SERCOP: {e}")
                return {"tiene_alerta": False, "resultado": "NO", "ruta_pdf": "", "mensaje_certificado": ""}

        return {"tiene_alerta": None, "resultado": "INDETERMINADO"}

    def _descargar_certificado(self, page: Page, cliente: Cliente, tipo_certificado: str) -> tuple[bytes, str]:
        """
        Clic en "Emitir Certificado" dispara un alert() nativo, y luego
        NAVEGA LA MISMA PÁGINA (no abre pestaña nueva, como se asumía
        originalmente) hacia la vista con el PDF embebido en un iframe.
        """
        codigo_certificado = {"valor": ""}

        def _manejar_dialogo(dialog):
            codigo_certificado["valor"] = dialog.message
            dialog.accept()

        page.on("dialog", _manejar_dialogo)

        page.click("a:has-text('Emitir Certificado')")
        page.wait_for_selector("#divPDF iframe", state="visible", timeout=15000)

        iframe_pdf = page.locator("#divPDF iframe")
        url_pdf = iframe_pdf.get_attribute("src")

        respuesta = page.context.request.get(url_pdf)
        page.remove_listener("dialog", _manejar_dialogo)

        if not respuesta.ok:
            raise ScraperError(
                f"[{self.nombre_sitio}] Falló la descarga del certificado (status {respuesta.status})",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        return respuesta.body(), codigo_certificado["valor"]