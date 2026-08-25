"""
Declaraciones Juradas (Contraloría). Solo se busca por cédula + apellidos
y nombres (NUNCA RUC) - para Jurídica, requiere la identificación del
representante legal (cadena pendiente).

Captcha visual clásico (imagen con código a escribir), embebido como
base64 en el propio HTML - se resuelve con el método "normal" de
2Captcha (distinto a recaptcha/hcaptcha/altcha ya usados en el proyecto).
"""

from playwright.sync_api import Page

import unicodedata
import re
from datetime import datetime

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona
from config.settings import cargar_infra_config
from src.captcha.resolver import resolver_captcha_imagen_con_2captcha, CaptchaResolverError


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
        Intenta resolver el captcha de imagen automaticamente con
        2Captcha; si falla o no esta habilitado, cae a pausa manual.
        """
        infra = cargar_infra_config()
        if infra.captcha_enabled and infra.captcha_api_key:
            try:
                resolver_captcha_imagen_con_2captcha(page, infra.captcha_api_key, "#captcha", "#x")
                if page.locator("#x").input_value().strip():
                    print(f"[{self.nombre_sitio}] Captcha de imagen resuelto automáticamente.\n")
                    self.delay_humano(0.5, 1.0)
                    return
            except CaptchaResolverError as e:
                print(f"[{self.nombre_sitio}] 2Captcha falló: {e} - cayendo a manual...\n")
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
            if boton_siguiente.count() == 0:
                break  # no hay paginacion - una sola pagina de resultados
            clase_siguiente = boton_siguiente.get_attribute("class") or ""
            if "disabled" in clase_siguiente:
                break  # no hay más páginas

            boton_siguiente.click()
            numero_pagina += 1
            self.delay_humano(1.0, 1.5)

        return resultados

    def _parsear_anio(self, texto_anio: str) -> int | None:
        """Extrae el primer numero de 4 digitos del texto de año -
        defensivo por si viene con texto adicional pegado."""
        coincidencia = re.search(r"(\d{4})", texto_anio or "")
        return int(coincidencia.group(1)) if coincidencia else None

    def _normalizar_texto(self, texto: str) -> str:
        """Normaliza SOLO para comparar/agrupar (nunca para mostrar):
        sin tildes, mayusculas, espacios colapsados. Corrige
        inconsistencias reales del propio portal (confirmado con
        evidencia: 'AUTONOMO' en 2025 vs 'AUTÓNOMO' en 2024/2023 para
        la misma entidad)."""
        texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
        return " ".join(texto.upper().split())

    def resumir_declaraciones(self, resultados: list[dict]) -> dict:
        if not resultados:
            return {
                "posee_declaraciones": "NO", "vigencia": "Desactualizado",
                "cargo": "-", "tiempo": "-", "ultimo_anio_en_cargo": "-",
            }

        anio_actual = datetime.now().year
        anios_vigentes = {anio_actual, anio_actual - 1, anio_actual - 2}

        def clave_normalizada(r):
            return f"{self._normalizar_texto(r['cargo'])} - {self._normalizar_texto(r['entidad'])}"

        def texto_original(r):
            return f"{r['cargo']} - {r['entidad']}"

        vigentes = [r for r in resultados if self._parsear_anio(r["año"]) in anios_vigentes]

        if not vigentes:
            return {
                "posee_declaraciones": "SI", "vigencia": "Desactualizado",
                "cargo": "-", "tiempo": "-", "ultimo_anio_en_cargo": "-",
            }

        vigentes_ordenados = sorted(vigentes, key=lambda r: self._parsear_anio(r["año"]), reverse=True)

        claves_vistas = []
        textos_vigencia = []
        for r in vigentes_ordenados:
            clave = clave_normalizada(r)
            if clave not in claves_vistas:
                claves_vistas.append(clave)
                textos_vigencia.append(texto_original(r))

        registro_mas_reciente = vigentes_ordenados[0]
        clave_actual = clave_normalizada(registro_mas_reciente)

        # Tiempo se cuenta SOLO dentro de la ventana de 3 anos vigentes,
        # no del historico completo - confirmado con evidencia real
        # (caso Alvarez Henriques: 2023 no cuenta aunque sea el mismo cargo).
        anios_en_ese_cargo = {
            self._parsear_anio(r["año"]) for r in vigentes
            if clave_normalizada(r) == clave_actual and self._parsear_anio(r["año"]) is not None
        }

        return {
            "posee_declaraciones": "SI",
            "vigencia": " / ".join(textos_vigencia),
            "cargo": texto_original(registro_mas_reciente),
            "tiempo": str(len(anios_en_ese_cargo)),
            "ultimo_anio_en_cargo": str(max(anios_en_ese_cargo)),
        }