"""
Scraper del Sitio 2 (Fiscalía - SIAF, Noticias del Delito).

El sitio cambio de formulario y de URL (confirmado 2026-08-26). Antes
usaba un campo generico "#pwd" que aceptaba cedula/RUC/nombre
indistintamente, navegando primero al totem y haciendo clic en un
enlace. El sitio nuevo tiene un <select> explicito de criterio de
busqueda ("cedula", "ruc", "nombre", etc.) y se accede por una URL
directa (redirect.php con parametro data= codificado, aparentemente
temporal segun el usuario).

Para personas Naturales: validación triple (cédula + RUC derivado +
nombre completo), igual criterio que Sitio 1 - pero ahora cada
busqueda selecciona su propio criterio explicito en vez de confiar en
que el campo generico adivine el tipo de dato.

url_base_totem se mantiene en la firma por compatibilidad con main.py,
pero ya NO se usa en este flujo (el sitio nuevo no requiere pasar por
el totem) - queda como legado, revisar si sigue haciendo falta para
otro flujo de Fiscalía.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, Denuncia, TipoPersona
from src.procesamiento.normalizacion import normalizar_texto_busqueda
from src.documentos.evidencia import capturar_evidencia

ID_SELECT_CRITERIO = "#tipoBusqueda"
ID_CAMPO_BUSQUEDA = "#valorBusqueda"
ID_BOTON_BUSCAR = "#btnBuscar"
ID_CONTENEDOR_RESULTADOS = "#resultados"
ID_CONTENEDOR_PAGINACION = "#paginacion"


class ScraperFiscalia(BaseScraper):
    nombre_sitio = "Fiscalía"

    def __init__(self, context, url_base: str, url_base_totem: str):
        super().__init__(context, url_base)
        self.url_base_totem = url_base_totem  # legado, ya no se usa en este flujo

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> list[Denuncia]:
        denuncias_encontradas = {}

        def _registrar(denuncias: list[Denuncia]):
            for d in denuncias:
                denuncias_encontradas[d.numero_noticia_delito] = d

        usar_derivacion = (
            cliente.tipo_persona == TipoPersona.NATURAL
            or cliente.es_juridica_con_ruc_persona_natural
        )

        if usar_derivacion:
            cedula_real = (
                cliente.identificacion if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion[:10]
            )
            ruc_real = (
                f"{cliente.identificacion}001" if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion
            )

            _registrar(self._buscar_una_vez(page, cliente, "cedula", cedula_real))
            _registrar(self._buscar_una_vez(page, cliente, "ruc", ruc_real))

            nombre_normalizado = normalizar_texto_busqueda(cliente.nombres_completos)
            _registrar(self._buscar_una_vez(page, cliente, "nombre", nombre_normalizado))

        else:
            # Jurídica real (con RazonSocial propia): razón social primero,
            # RUC como fallback si no hay resultados.
            nombre_normalizado = normalizar_texto_busqueda(cliente.razon_social)
            denuncias_por_nombre = self._buscar_una_vez(page, cliente, "nombre", nombre_normalizado)

            if denuncias_por_nombre:
                _registrar(denuncias_por_nombre)
            else:
                print(f"[{cliente.identificacion}] Sin resultados por razón social en Fiscalía, probando por RUC...")
                denuncias_por_ruc = self._buscar_una_vez(page, cliente, "ruc", cliente.identificacion)
                _registrar(denuncias_por_ruc)

        return list(denuncias_encontradas.values())

    def _buscar_una_vez(self, page: Page, cliente: Cliente, criterio: str, texto_busqueda: str) -> list[Denuncia]:
        """
        criterio: uno de "cedula", "ruc", "nombre" (valores reales del
        <select> del sitio nuevo - ya no hace falta adivinar que tipo
        de dato acepta un campo generico como antes).
        """
        page.goto(self.url_base)
        self.delay_humano()

        page.select_option(ID_SELECT_CRITERIO, criterio)
        self.delay_humano(0.3, 0.6)

        page.fill(ID_CAMPO_BUSQUEDA, texto_busqueda)
        self.verificar_campo_lleno(page, ID_CAMPO_BUSQUEDA, texto_busqueda)
        self.delay_humano(0.5, 1.0)

        page.click(ID_BOTON_BUSCAR)
        self.delay_humano(1.5, 2.5)

        # "Sin resultados" se muestra como modal SweetAlert2, NO como
        # #resultados vacio - hay que detectarlo y cerrarlo con "Aceptar"
        # antes de seguir, o el modal se queda tapando la pantalla para
        # la siguiente busqueda. Confirmado con evidencia real 2026-08-26.
        modal_sin_resultados = page.locator(".swal2-popup:has-text('Sin resultados')")
        if modal_sin_resultados.count() > 0:
            page.locator(".swal2-confirm").click()
            self.delay_humano(0.3, 0.6)
            return []

        total_paginas = self._obtener_total_paginas(page)
        denuncias_todas = []

        for numero_pagina in range(1, total_paginas + 1):
            if numero_pagina > 1:
                page.locator(f'a[onclick="mostrarPagina({numero_pagina}); return false;"]').first.click()
                self.delay_humano(1.0, 1.5)

            self._expandir_todos_los_involucrados(page)

            capturar_evidencia(
                page, cliente.identificacion_evidencia or cliente.identificacion,
                sitio=f"sitio2_fiscalia_noticias_pagina{numero_pagina}", carpeta_sitio="fiscalia",
                subcarpeta=cliente.subcarpeta_evidencia,
            )
            denuncias_todas.extend(self._extraer_denuncias(page, cliente))

        return denuncias_todas

    def _expandir_todos_los_involucrados(self, page: Page) -> None:
        """
        Los paneles de 'Involucrados' de cada tarjeta empiezan colapsados
        por defecto - hay que expandirlos TODOS antes de leer el texto,
        porque inner_text() devuelve vacío para contenido oculto por CSS.
        Se re-consulta el selector en CADA vuelta (no una lista fija con
        .all()) porque hacer clic en un boton cambia su aria-expanded a
        'true' y puede haber timing/animacion que bloquee un indice fijo
        - confirmado con evidencia real: un TimeoutError esperando el
        segundo boton de una lista precomputada.
        """
        intentos_maximos = 20  # limite defensivo, nunca deberia haber tantas denuncias
        for _ in range(intentos_maximos):
            boton = page.locator(
                f"{ID_CONTENEDOR_RESULTADOS} button.btn-involucrados[aria-expanded='false']"
            ).first
            if boton.count() == 0:
                break
            try:
                boton.click(timeout=5000)
            except Exception as e:
                print(f"    [advertencia] no se pudo expandir un panel de involucrados: {type(e).__name__} - continuando con el resto")
                break
            page.wait_for_timeout(300)

    def _obtener_total_paginas(self, page: Page) -> int:
        """
        Lee los links numericos de #paginacion y toma el mayor como
        total de paginas. Si no existe el bloque de paginacion (pocos
        resultados, una sola pagina), devuelve 1. Los links "Siguiente"/
        "Ultima"/"Anterior"/"Primera" (si existen) se descartan por no
        ser numericos.
        """
        if page.locator(ID_CONTENEDOR_PAGINACION).count() == 0:
            return 1

        textos = page.locator(f"{ID_CONTENEDOR_PAGINACION} a.page-link").all_inner_texts()
        numeros = [int(t.strip()) for t in textos if t.strip().isdigit()]
        return max(numeros) if numeros else 1

    def _extraer_denuncias(self, page: Page, cliente: Cliente) -> list[Denuncia]:
        tarjetas = page.locator(f"{ID_CONTENEDOR_RESULTADOS} > div.card").all()

        denuncias = []
        for tarjeta in tarjetas:
            header = tarjeta.locator(".card-header").first.inner_text()
            numero = header.replace("NOTICIA DEL DELITO Nro.", "").strip()

            tabla_datos = tarjeta.locator("table.tabla-compacta").first
            lugar = self._valor_por_etiqueta(tabla_datos, "LUGAR")
            fecha = self._valor_por_etiqueta(tabla_datos, "FECHA")
            delito = self._valor_por_etiqueta(tabla_datos, "DELITO")
            unidad = self._valor_por_etiqueta(tabla_datos, "UNIDAD")

            tabla_sujetos = tarjeta.locator(".involucrados-panel table").first
            filas_sujetos = tabla_sujetos.locator("tbody tr").all()

            estado_rol_cliente = ""
            nombres_sospechosos = []
            roles_sospechoso = ("SOSPECHOSO", "SOSPECHOSO NO RECONOCIDO")

            for fila in filas_sujetos:
                celdas = fila.locator("td").all_inner_texts()
                if len(celdas) < 3:
                    continue
                cedula_fila, nombre_fila, estado_fila = celdas[0].strip(), celdas[1].strip(), celdas[2].strip()

                if cedula_fila == cliente.identificacion:
                    estado_rol_cliente = estado_fila
                if estado_fila.strip().upper() in roles_sospechoso:
                    nombres_sospechosos.append(nombre_fila)

            nombre_sospechoso = "; ".join(nombres_sospechosos)

            denuncias.append(Denuncia(
                numero_noticia_delito=numero,
                lugar=lugar,
                fecha=fecha,
                delito=delito,
                estado_rol_cliente=estado_rol_cliente,
                nombre_sospechoso=nombre_sospechoso,
                unidad_fiscalia=unidad,
            ))

        return denuncias

    def _valor_por_etiqueta(self, tabla, texto_etiqueta: str) -> str:
        """
        El sitio nuevo usa <th>ETIQUETA</th><td>VALOR</td> en la MISMA
        fila (antes eran filas separadas) - se busca el <th>, no el <td>.
        """
        celda_th = tabla.locator(f"th:has-text('{texto_etiqueta}')").first
        if celda_th.count() == 0:
            return ""
        siguiente = celda_th.locator("xpath=following-sibling::td[1]")
        return siguiente.inner_text().strip() if siguiente.count() > 0 else ""