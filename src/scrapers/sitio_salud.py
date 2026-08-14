"""
Cobertura de Salud (MSP) - React/Material-UI. El resultado se muestra
como un PDF incrustado (blob), NO como datos HTML - se debe interceptar
la respuesta de red que genera ese PDF, mismo patrón que otros sitios.

LIMITACIÓN CONFIRMADA: este portal SOLO acepta cédula (10 dígitos), no
RUC. Para clientes Jurídica, se requiere la cédula del representante
legal - funcionalidad pendiente (cadena de representantes, pausada).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, Salud, TipoPersona
from src.documentos.almacenamiento import guardar_pdf_local


class ScraperSalud(BaseScraper):
    """
    Cobertura de Salud (MSP).

    REQUISITO ESPECIAL: este sitio SOLO funciona con Chrome real
    instalado en la máquina (channel="chrome" al lanzar el navegador),
    NO con el Chromium portable/aislado que usa el resto del proyecto.
    Confirmado empíricamente: con Chromium portable, la conexión nunca
    se establece (net::ERR_TIMED_OUT desde about:blank, incluso con
    ignore_https_errors=True) - con Chrome real del sistema, conecta sin
    problema. Causa exacta no confirmada (sospecha: inspección de tráfico
    de la VPN corporativa distingue el binario aislado del real).

    Quien orqueste este scraper (main.py) debe lanzar el navegador con
    channel="chrome" específicamente para este sitio - los demás 7
    sitios del proyecto siguen usando el Chromium portable normal.
    """
    nombre_sitio = "Cobertura de Salud"

    def tiene_captcha(self, page: Page) -> bool:
        # TODO: no se ha confirmado si este portal presenta captcha.
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> Salud:
        if cliente.tipo_persona == TipoPersona.JURIDICA:
            raise ScraperError(
                f"[{self.nombre_sitio}] Este portal solo acepta cédula de persona "
                f"natural - requiere la cédula del representante legal "
                f"(funcionalidad pendiente).",
                resultado=ResultadoConsulta.SIN_DATOS,
            )

        # Paso 1: cargar la página, con reintento automático si se queda
        # atascada - confirmado empíricamente que la carga a veces no
        # progresa nunca del todo, incluso con timeout generoso, y
        # requería una recarga manual (F5) para completarse.
        pagina_lista = False
        for intento in range(1, 3):
            try:
                page.goto(self.url_base, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_selector("#cedula", state="visible", timeout=20000)

                # El campo de cédula existe desde el principio, pero NO
                # indica que React ya esté completamente lista - se usa
                # el autocompletado del campo de fecha como señal real.
                page.wait_for_function(
                    """() => {
                        const campoFecha = document.querySelector('input[placeholder="DD-MM-YYYY"]');
                        return campoFecha && campoFecha.value.trim().length > 0;
                    }""",
                    timeout=30000,
                )
                pagina_lista = True
                break
            except Exception as e:
                print(f"    [{self.nombre_sitio}] Intento {intento}/2 de carga falló: {type(e).__name__} - reintentando con recarga...")
                continue

        if not pagina_lista:
            raise ScraperError(
                f"[{self.nombre_sitio}] La página no terminó de cargar tras 2 intentos.",
                resultado=ResultadoConsulta.TIMEOUT,
            )

        self.delay_humano(0.5, 1.0)

        # Paso 2: ingresar cédula, esperar a que el botón Consultar se
        # habilite (confirma que el formulario validó el dato ingresado).
        page.fill("#cedula", cliente.identificacion)
        boton_consultar = page.locator("button:has-text('Consultar')")
        boton_consultar.wait_for(state="visible", timeout=10000)
        for _ in range(20):  # hasta 6 segundos esperando habilitación
            if boton_consultar.is_enabled():
                break
            page.wait_for_timeout(300)
        self.delay_humano(0.5, 1.0)

        # Paso 3: buscar - clic y esperar a que la respuesta del blob PDF
        # sea detectada (confirma que el servidor ya generó el documento).
        resultado_captura = {"blob_url": None}

        def _en_respuesta(response):
            if resultado_captura["blob_url"] is None:
                try:
                    if response.url.startswith("blob:") and "pdf" in response.headers.get("content-type", "").lower():
                        resultado_captura["blob_url"] = response.url
                except Exception:
                    pass

        page.on("response", _en_respuesta)
        try:
            boton_consultar.click()
            for _ in range(40):  # hasta 20 segundos esperando el blob
                if resultado_captura["blob_url"] is not None:
                    break
                page.wait_for_timeout(500)
        finally:
            page.remove_listener("response", _en_respuesta)

        pdf_bytes = None
        if resultado_captura["blob_url"] is not None:
            # Paso 4: el blob ya fue detectado por la red, pero el visor
            # de PDF (extensión de Chrome) puede tardar un poco más en
            # terminar de renderizar visualmente - se espera a que el
            # visor esté presente en el DOM antes de leer el blob y
            # antes de la captura de pantalla.
            try:
                page.wait_for_selector("embed[type='application/pdf']", state="visible", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(1000)  # margen final corto, tras confirmar visor visible

            try:
                pdf_base64 = page.evaluate(
                    """async (blobUrl) => {
                        const respuesta = await fetch(blobUrl);
                        const buffer = await respuesta.arrayBuffer();
                        const bytes = new Uint8Array(buffer);
                        let binario = '';
                        for (let i = 0; i < bytes.length; i++) {
                            binario += String.fromCharCode(bytes[i]);
                        }
                        return btoa(binario);
                    }""",
                    resultado_captura["blob_url"],
                )
                import base64
                pdf_bytes = base64.b64decode(pdf_base64)
            except Exception as e:
                print(f"[{cliente.identificacion}] Falló extracción del blob PDF: {e}")
        else:
            print(f"[{cliente.identificacion}] El PDF no llegó a generarse tras 20s de espera.")

        resultado = Salud()
        if pdf_bytes is not None:
            ruta_guardada = guardar_pdf_local(pdf_bytes, cliente.identificacion, "cobertura_salud")
            resultado.ruta_pdf = ruta_guardada

            try:
                situacion_laboral, tipo_afiliacion = self._extraer_cobertura_del_pdf(pdf_bytes)
                resultado.situacion_laboral = situacion_laboral
                resultado.tipo_afiliacion = tipo_afiliacion
            except Exception as e:
                print(f"[{cliente.identificacion}] Falló extracción de la tabla de cobertura: {e}")
        else:
            print(f"[{cliente.identificacion}] No se pudo capturar el PDF de cobertura de salud (solo evidencia visual disponible).")

        return resultado

    def _extraer_cobertura_del_pdf(self, pdf_bytes: bytes) -> tuple[str, str]:
        """
        Extrae la tabla real del PDF (Seguro | Tipo de seguro | Mensaje |
        Registro de Cobertura) usando pdfplumber, que respeta la
        estructura de columnas del documento - un parseo de texto plano
        (pypdf) no permite distinguir de forma confiable dónde termina
        "Tipo de seguro" y empieza "Mensaje", ya que ambas son texto
        libre sin delimitador claro en la extracción lineal.

        Busca la fila donde "Registro de Cobertura" diga "si registra
        cobertura", y devuelve (situacion_laboral, tipo_afiliacion) para
        esa fila. Si ninguna fila tiene cobertura activa, devuelve textos
        indicando "sin cobertura".
        """
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tabla = pdf.pages[0].extract_tables()[0]

        # tabla[0] es el encabezado; las filas de datos empiezan en tabla[1]
        for fila in tabla[1:]:
            if len(fila) < 4:
                continue
            seguro, tipo_seguro, _mensaje, registro_cobertura = fila[0], fila[1], fila[2], fila[3]
            if registro_cobertura and "si registra cobertura" in registro_cobertura.strip().lower():
                situacion_laboral = f"Relación de Dependencia ({seguro.strip()})"
                tipo_afiliacion = tipo_seguro.strip().replace("\n", " ")
                return situacion_laboral, tipo_afiliacion

        return "Sin cobertura activa", ""