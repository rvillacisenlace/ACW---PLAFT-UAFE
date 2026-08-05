"""
Clase base para todos los scrapers de portal.

Por qué existe esta capa (spec, "Criterio de Diseño" y "Manejo de Excepciones"):
- Modularidad: cada sitio hereda de aquí. Si Sitio 2 cambia su HTML y explota,
  el orquestador (main.py) debe poder capturar esa excepción SIN que tumbe
  la ejecución de Sitio 1 para el resto de clientes.
- Comportamiento humano: delays dinámicos y fingerprint del navegador van aquí,
  una sola vez, para que ningún scraper individual "se olvide" de aplicarlos.
- Reintentos: los portales gubernamentales son inestables (spec lo advierte
  explícitamente), así que el retry con backoff vive en la base, no se repite
  copiado en cada sitio.
"""
import random
from sys import exception
import time
from abc import ABC, abstractmethod
from playwright.sync_api import BrowserContext, Page, sync_playwright
from pytest_playwright.pytest_playwright import browser_name
from src.core.models import Cliente, ProcesoJudicial, ResultadoConsulta

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

    def delay_humano(self, min_s: float = 0.8, max_s: float = 2.4) -> None:
        """Pausa aleatoria entre acciones. No usar time.sleep fijo en ningún scraper."""
        time.sleep(random.uniform(min_s, max_s))

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
    def buscar_cliente(self, page: Page, cliente: Cliente) -> list[ProcesoJudicial]:
        """Cada sitio implementa su propia lógica de búsqueda y extracción."""
        raise NotImplementedError

    @abstractmethod
    def tiene_captcha(self, page: Page) -> bool:
        """Detecta si el portal presentó un captcha en esta carga de página."""
        raise NotImplementedError