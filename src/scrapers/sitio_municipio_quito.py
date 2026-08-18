"""
Municipio de Quito - Consulta de valores pendientes de pago.
Búsqueda por Apellidos y Nombres / Razón social (NO cédula/RUC).
Captcha de imagen - resolución MANUAL (2Captcha pausado en todo el
proyecto hasta aprobación de presupuesto).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona
from src.documentos.evidencia import capturar_evidencia
from src.core.models import Cliente, ResultadoConsulta, DeudaMunicipal, TipoPersona

class ScraperMunicipioQuito(BaseScraper):
    nombre_sitio = "Municipio de Quito"

    def tiene_captcha(self, page: Page) -> bool:
        return page.locator("#TcOpciones_TbpApellidosNombres_TxtCaptchaApellidosNombres").count() > 0

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        nombre_o_razon_social = (
            cliente.nombres_completos if cliente.tipo_persona == TipoPersona.NATURAL
            else cliente.razon_social
        )

        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        page.click("#__tab_TcOpciones_TbpApellidosNombres")
        self.delay_humano(0.5, 1.0)

        page.fill("#TcOpciones_TbpApellidosNombres_TxtApellidosNombres", nombre_o_razon_social)
        self.delay_humano(0.5, 1.0)

        self._resolver_captcha_manual(page)

        page.click("#TcOpciones_TbpApellidosNombres_LkbConsultarApellidosNombres")
        self.delay_humano(2.0, 3.0)

        # Puede haber múltiples resultados si el nombre coincide con
        # variantes (ej. "TORRES GORDILLO DIEGO PATRICIO" y "TORRES
        # GORDILLO DIEGO PATRICIO Y OTROS" - copropiedad). Se filtra
        # explícitamente por la fila cuyo texto coincide EXACTO con el
        # nombre completo del cliente, excluyendo variantes.
        nombre_normalizado = nombre_o_razon_social.strip().upper()
        filas = page.locator("tr").filter(has=page.locator("img.Boton.Lupa"))
        indice_fila_exacta = None

        for i in range(filas.count()):
            fila = filas.nth(i)
            texto_fila = fila.inner_text().strip().upper()
            primera_columna = texto_fila.split("\t")[0].strip()
            if primera_columna == nombre_normalizado:
                indice_fila_exacta = i
                break

        if indice_fila_exacta is None:
            # No hay coincidencia exacta - solo variantes (ej. "Y OTROS").
            # Se trata igual que "no registrado": sin deuda, sin error,
            # continuando con el resto del flujo (decisión de negocio
            # confirmada).
            capturar_evidencia(page, cliente.identificacion, sitio="sitio_municipio_quito_resultado", carpeta_sitio="municipio_quito")
            return DeudaMunicipal(
                registrado=False,
                mensaje="Sin coincidencia exacta del nombre",
                tiene_deuda=False,
                valor_total="$0.00",
            )

        # Se hace clic sobre el enlace <a href="/ListadoObligaciones/{i}/">,
        # no directamente sobre el <img>, para evitar el atributo
        # "aria-describedby" del tooltip que cambia dinámicamente y podía
        # interferir con la identificación estable del elemento.
        enlace_ver = page.locator(f"a[href='/ListadoObligaciones/{indice_fila_exacta}/']")
        enlace_ver.click()
        self.delay_humano(1.5, 2.5)

        return self._extraer_resultado(page, cliente)

    def _resolver_captcha_manual(self, page: Page) -> None:
        print(f"\n{'='*60}")
        print(f"CAPTCHA VISUAL - {self.nombre_sitio}")
        print(f"Escribe el código de la imagen en el navegador.")
        input("Cuando termines, presiona ENTER aquí para continuar...")
        print(f"{'='*60}\n")

    def _extraer_resultado(self, page: Page, cliente: Cliente) -> DeudaMunicipal:
        # Caso 1: no existe ningún registro para el nombre/razón social
        # ingresado (distinto de "registrado pero sin deuda"). Se
        # captura evidencia y se lee el mensaje ANTES de cerrar el modal
        # con "Aceptar" (confirmado que no se cierra solo).
        if page.locator("#lblMensaje").count() > 0:
            texto_mensaje = page.locator("#lblMensaje").inner_text().strip()
            capturar_evidencia(page, cliente.identificacion, sitio="sitio_municipio_quito_resultado", carpeta_sitio="municipio_quito")

            try:
                page.locator("#btnAceptarMensaje").click()
                self.delay_humano(0.5, 1.0)
            except Exception:
                pass

            return DeudaMunicipal(registrado=False, mensaje=texto_mensaje, tiene_deuda=False, valor_total="$0.00")

        # Caso 2: registrado, pero sin deuda pendiente.
        if page.locator("#lblMensajeSinDeuda").count() > 0:
            capturar_evidencia(page, cliente.identificacion, sitio="sitio_municipio_quito_resultado", carpeta_sitio="municipio_quito")
            return DeudaMunicipal(registrado=True, tiene_deuda=False, valor_total="$0.00")

        # Caso 3: registrado, con deuda.
        try:
            valor_total = page.locator("tr.listado__fila__Total span").inner_text().strip()
        except Exception:
            valor_total = ""

        capturar_evidencia(page, cliente.identificacion, sitio="sitio_municipio_quito_resultado", carpeta_sitio="municipio_quito")

        tiene_deuda = valor_total not in ("$0.00", "")
        return DeudaMunicipal(registrado=True, tiene_deuda=tiene_deuda, valor_total=valor_total)