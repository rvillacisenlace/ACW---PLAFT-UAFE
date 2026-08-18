"""
Declaraciones Juradas (Contraloría). Solo se busca por cédula + apellidos
y nombres (NUNCA RUC) - para Jurídica, requiere la identificación del
representante legal (cadena pendiente).

Captcha visual clásico (imagen con código a escribir), embebido como
base64 en el propio HTML - se resuelve con el método "normal" de
2Captcha (distinto a recaptcha/hcaptcha/altcha ya usados en el proyecto).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona
from config.settings import cargar_infra_config


class ScraperContraloria(BaseScraper):
    nombre_sitio = "Contraloría - Declaraciones Juradas"

    def tiene_captcha(self, page: Page) -> bool:
        return page.locator("#captcha").count() > 0

    def buscar_cliente(self, page: Page, cliente: Cliente) -> list[dict]:
        if cliente.tipo_persona == TipoPersona.JURIDICA:
            raise ScraperError(
                f"[{self.nombre_sitio}] Este portal solo acepta cédula/nombre de "
                f"persona natural - requiere la identificación del representante "
                f"legal (funcionalidad de cadena de representantes pendiente).",
                resultado=ResultadoConsulta.SIN_DATOS,
            )

        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Se busca SIEMPRE por cédula primero (si está disponible); solo
        # se usa el campo de nombre completo como respaldo si no hay
        # cédula. Nunca se llenan ambos campos a la vez.
        if cliente.identificacion:
            page.fill("#txtCedula", cliente.identificacion)
        elif cliente.nombres_completos:
            page.fill("#txtNombres", cliente.nombres_completos)
        else:
            raise ScraperError(
                f"[{self.nombre_sitio}] El cliente no tiene ni identificación ni nombre completo para buscar.",
                resultado=ResultadoConsulta.SIN_DATOS,
            )
        self.delay_humano(0.5, 1.0)

        self._resolver_captcha_visual(page)

        page.click("#btnBuscar_in")
        self.delay_humano(2.0, 3.5)

        return self._extraer_resultados(page, cliente)

    def _resolver_captcha_visual(self, page: Page) -> None:
        """
        DECISIÓN DE NEGOCIO (pendiente de aprobación de presupuesto):
        todos los captchas de este proyecto se resuelven MANUALMENTE por
        ahora, no vía 2Captcha - se implementará la resolución automática
        de pago una vez aprobado el gasto correspondiente.

        Pausa hasta 2 minutos esperando que la persona escriba el código
        manualmente en el campo #x y presione Enter o haga clic en
        Buscar - se detecta que ya se resolvió cuando el campo #x deja
        de estar vacío.
        """
        print(f"\n{'='*60}")
        print(f"CAPTCHA VISUAL - Se requiere intervención manual")
        print(f"Escribe el código de la imagen en el campo del navegador.")
        print(f"Tienes 120 segundos.")
        input("Cuando termines, presiona ENTER aquí para continuar...")
        print(f"{'='*60}\n")

        campo_codigo = page.locator("#x")
        for _ in range(40):  # hasta 120 segundos (40 x 3s)
            page.wait_for_timeout(3000)
            valor_actual = campo_codigo.input_value()
            if valor_actual.strip():
                print("Código ingresado - continuando automáticamente.\n")
                self.delay_humano(0.5, 1.0)
                return

        raise ScraperError(
            f"[{self.nombre_sitio}] Captcha visual sin resolución dentro del tiempo límite.",
            resultado=ResultadoConsulta.ERROR_CAPTCHA,
        )

    def _extraer_resultados(self, page: Page, cliente: Cliente) -> list[dict]:
        """
        Extrae la tabla de resultados y captura evidencia de cada página
        (paginación con "Siguiente" si aplica - tabla DataTables estándar).
        Maneja explícitamente el caso "Sin resultados" (confirmado con
        HTML real: celda única con class="dataTables_empty").
        """
        from src.documentos.evidencia import capturar_evidencia

        resultados = []
        numero_pagina = 1

        while True:
            self.delay_humano(1.0, 1.5)

            capturar_evidencia(
                page, cliente.identificacion,
                sitio=f"sitio_contraloria_pagina{numero_pagina}",
                carpeta_sitio="contraloria"
            )

            if page.locator("td.dataTables_empty").count() > 0:
                break  # "Sin resultados" - tabla vacía por diseño, no un error

            filas = page.locator("#tblBusquedaResultados tbody tr").all()
            for fila in filas:
                celdas = fila.locator("td").all_inner_texts()
                if len(celdas) >= 4:
                    resultados.append({
                        "apellidos_nombres": celdas[0].strip(),
                        "cargo": celdas[1].strip(),
                        "entidad": celdas[2].strip(),
                        "año": celdas[3].strip(),
                    })

            boton_siguiente = page.locator("#tblBusquedaResultados_next")
            clase_siguiente = boton_siguiente.get_attribute("class") or ""
            if "disabled" in clase_siguiente:
                break  # no hay más páginas

            boton_siguiente.click()
            numero_pagina += 1
            self.delay_humano(1.0, 1.5)

        return resultados