"""
Scraper del Sitio 2 (Fiscalía - SIAF).
Para personas Naturales: validación triple (cédula + RUC derivado + nombre
completo), igual criterio que Sitio 1. El campo único 'pwd' acepta
cédula, RUC, o nombre indistintamente.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, Denuncia, TipoPersona
from src.procesamiento.normalizacion import normalizar_texto_busqueda
from src.documentos.evidencia import capturar_evidencia

ID_CAMPO_BUSQUEDA = "#pwd"
ID_BOTON_BUSCAR = "#btn_buscar_denuncia"
ID_CONTENEDOR_RESULTADOS = "#resultados"


class ScraperFiscalia(BaseScraper):
    nombre_sitio = "Fiscalía"

    def __init__(self, context, url_base: str, url_base_totem: str):
        super().__init__(context, url_base)
        self.url_base_totem = url_base_totem

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

            _registrar(self._buscar_una_vez(page, cliente, cedula_real))
            _registrar(self._buscar_una_vez(page, cliente, ruc_real))

            nombre_normalizado = normalizar_texto_busqueda(cliente.nombres_completos)
            _registrar(self._buscar_una_vez(page, cliente, nombre_normalizado))

        else:
            # Jurídica real (con RazonSocial propia): razón social primero,
            # RUC como fallback si no hay resultados - mismo criterio que
            # Sitio 1, que ya tenía este fallback y Sitio 2 no lo tenía.
            nombre_normalizado = normalizar_texto_busqueda(cliente.razon_social)
            denuncias_por_nombre = self._buscar_una_vez(page, cliente, nombre_normalizado)

            if denuncias_por_nombre:
                _registrar(denuncias_por_nombre)
            else:
                print(f"[{cliente.identificacion}] Sin resultados por razón social en Fiscalía, probando por RUC...")
                denuncias_por_ruc = self._buscar_una_vez(page, cliente, cliente.identificacion)
                _registrar(denuncias_por_ruc)

        return list(denuncias_encontradas.values())

    def _buscar_una_vez(self, page: Page, cliente: Cliente, texto_busqueda: str) -> list[Denuncia]:
        page.goto(self.url_base_totem)
        self.delay_humano()
        page.click("a[href='noticiasdelito/index.php']")
        self.delay_humano()

        page.fill(ID_CAMPO_BUSQUEDA, texto_busqueda)
        self.delay_humano(0.5, 1.0)

        with page.expect_response(lambda r: "info_mod.php" in r.url):
            page.click(ID_BOTON_BUSCAR)
        self.delay_humano(1.0, 1.5)

        capturar_evidencia(page, cliente.identificacion, sitio="sitio2_fiscalia", carpeta_sitio="fiscalia")
        return self._extraer_denuncias(page, cliente)

    def _extraer_denuncias(self, page: Page, cliente: Cliente) -> list[Denuncia]:
        bloques_noticia = page.locator(
            f"{ID_CONTENEDOR_RESULTADOS} th:has-text('NOTICIA DEL DELITO Nro.')"
        ).all()

        denuncias = []
        for bloque_header in bloques_noticia:
            texto_header = bloque_header.inner_text()
            numero = texto_header.replace("NOTICIA DEL DELITO Nro.", "").strip()

            tabla_caso = bloque_header.locator("xpath=ancestor::table[1]")

            lugar = self._valor_por_etiqueta(tabla_caso, "LUGAR")
            fecha = self._valor_por_etiqueta(tabla_caso, "FECHA")
            delito = self._valor_por_etiqueta(tabla_caso, "DELITO:")
            unidad = self._valor_por_etiqueta(tabla_caso, "UNIDAD:")

            tabla_sujetos = tabla_caso.locator("xpath=following-sibling::table[1]")
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

    def _valor_por_etiqueta(self, contenedor, texto_etiqueta: str) -> str:
        celda = contenedor.locator(f"td:has-text('{texto_etiqueta}')").first
        if celda.count() == 0:
            return ""
        siguiente = celda.locator("xpath=following-sibling::td[1]")
        return siguiente.inner_text().strip() if siguiente.count() > 0 else ""