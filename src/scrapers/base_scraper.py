"""
Clase base para todos los scrapers de portal.

Por qué existe esta capa:
- Modularidad: cada sitio hereda de aquí. Si un sitio cambia su HTML y
  explota, el orquestador debe poder capturar esa excepción SIN que
  tumbe la ejecución de los demás sitios para el resto de clientes.
- Comportamiento humano: delays dinámicos van aquí, una sola vez, para
  que ningún scraper individual "se olvide" de aplicarlos.
- Reintentos: los portales gubernamentales son inestables, así que el
  retry con backoff vive en la base, no se repite copiado en cada sitio.
"""
import random
import time
from abc import ABC, abstractmethod
from typing import Any
from playwright.sync_api import BrowserContext, Page
from src.core.models import Cliente, ResultadoConsulta
from src.core.models import Cliente, ResultadoConsulta, TipoPersona

def derivar_cedula_y_ruc(cliente: Cliente) -> tuple[str, str]:
    """
    Deriva la cédula (10 dígitos) y el RUC derivado (13 dígitos) de un
    cliente Natural, SIN asumir que cliente.identificacion siempre
    tiene 10 dígitos. Confirmado con evidencia real (2026-09-04): a
    veces la columna "Ruc / CI" del Excel ya trae el RUC completo (13
    dígitos) para un cliente marcado Natural - la lógica anterior
    (repetida en Sentenciados, Fiscalía y Función Judicial) siempre
    concatenaba "001" al valor crudo, produciendo un RUC de 16 dígitos
    sin sentido cuando la identificación ya venía con 13. Se detecta la
    longitud real en vez de asumir.

    También cubre el caso Jurídica-con-RUC-de-persona-natural (mismo
    criterio ya usado en varios scrapers vía
    cliente.es_juridica_con_ruc_persona_natural) - en ese caso
    identificacion YA es un RUC completo de 13 dígitos.
    """
    if cliente.tipo_persona == TipoPersona.NATURAL:
        if len(cliente.identificacion) >= 13:
            return cliente.identificacion[:10], cliente.identificacion
        return cliente.identificacion, f"{cliente.identificacion}001"
    else:
        return cliente.identificacion[:10], cliente.identificacion

class ScraperError(Exception):
    """Error específico de scraping, distinto de un error de programación."""
    def __init__(self, mensaje: str, resultado: ResultadoConsulta):
        super().__init__(mensaje)
        self.resultado = resultado


class BaseScraper(ABC):
    nombre_sitio: str = "sin_nombre"      # cada subclase lo sobreescribe
    max_reintentos: int = 3

    def __init__(self, context: BrowserContext, url_base: str):
        # url_base viene de la Hoja de Parametrización del Excel, nunca hardcodeada.
        self.context = context
        self.url_base = url_base

    # Factor de reduccion global de tiempos (2026-09-08, solicitado
    # para reducir el tiempo total por cliente). Se aplica UNA vez aqui
    # en vez de editar las 117 llamadas a delay_humano() repartidas en
    # 12+ archivos - reduce TODAS las esperas proporcionalmente,
    # incluyendo las que ya fueron ajustadas hoy en respuesta a bugs
    # reales de timing (SCVS Personas, Antecedentes Penales, etc.).
    # Si algun sitio empieza a fallar mas seguido despues de este
    # cambio, lo primero a sospechar es este factor - se puede subir
    # de vuelta a 1.0 (sin reduccion) facilmente.
    FACTOR_VELOCIDAD = 0.6

    def delay_humano(self, min_s: float = 0.8, max_s: float = 2.4) -> None:
        """Pausa aleatoria entre acciones. No usar time.sleep fijo en ningún scraper."""
        time.sleep(random.uniform(min_s * self.FACTOR_VELOCIDAD, max_s * self.FACTOR_VELOCIDAD))

    def ejecutar_con_reintentos(self, funcion, *args, **kwargs):
        """
        Envuelve cualquier paso del scraper (goto, submit, etc.) con reintentos
        y backoff. Un fallo aquí lanza ScraperError, que el orquestador captura
        por cliente/sitio sin detener el resto del flujo.
        """
        ultimo_error = None
        for intento in range(1, self.max_reintentos + 1):
            try:
                return funcion(*args, **kwargs)
            except Exception as e:
                ultimo_error = e
                espera = (2 ** intento) + random.uniform(0, 1)
                time.sleep(espera)
        raise ScraperError(
            f"[{self.nombre_sitio}] Falló tras {self.max_reintentos} intentos: {ultimo_error}",
            resultado=ResultadoConsulta.TIMEOUT,
        )

    @abstractmethod
    def buscar_cliente(self, page: Page, cliente: Cliente) -> Any:
        """
        Cada sitio implementa su propia lógica de búsqueda y extracción.
        El tipo de retorno es genérico (Any) a propósito: cada sitio
        devuelve una estructura de datos distinta (dict de datos de RUC,
        lista de procesos, etc.) - no hay un tipo único común entre los
        8 sitios de este proyecto.
        """
        raise NotImplementedError

    @abstractmethod
    def tiene_captcha(self, page: Page) -> bool:
        """Detecta si el portal presentó un captcha en esta carga de página."""
        raise NotImplementedError

    def verificar_campo_lleno(self, page: Page, selector: str, valor_esperado: str, timeout_ms: int = 5000) -> None:
        """
        Confirma que un campo de texto quedo con el valor exacto que se
        intento escribir, antes de aceptar cualquier conclusion de "no
        encontrado" como valida. Usa un timeout corto (5s, no los 30s
        default de Playwright) porque si el campo desaparecio/nunca
        aparecio, es mejor fallar rapido con un mensaje claro que
        esperar el timeout completo con un error crudo.
        """
        locator = page.locator(selector)
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            valor_real = locator.input_value().strip()
        except Exception as e:
            raise ScraperError(
                f"[{self.nombre_sitio}] El campo '{selector}' desapareció o nunca respondió "
                f"tras escribir '{valor_esperado}' ({type(e).__name__}) - fallo mecánico, no un "
                f"resultado real de 'no encontrado'.",
                resultado=ResultadoConsulta.ERROR_CAPTCHA,
            )
        if valor_real != valor_esperado.strip():
            raise ScraperError(
                f"[{self.nombre_sitio}] El campo '{selector}' quedó con '{valor_real}' "
                f"en vez de '{valor_esperado}' - fallo mecánico de escritura, no es un "
                f"resultado real de 'no encontrado'.",
                resultado=ResultadoConsulta.ERROR_CAPTCHA,
            )