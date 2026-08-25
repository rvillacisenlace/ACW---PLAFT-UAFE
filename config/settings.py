"""
Configuración central del proyecto.

Regla de diseño (spec, sección "Parametrización"):
- Los SECRETOS (client_id, client_secret, api keys) viven en variables de entorno (.env).
  Nunca en este archivo, nunca en el Excel.
- Los PARÁMETROS DE NEGOCIO (URLs de los portales, umbral de volumen, rutas de
  guardado en OneDrive, días de retención) viven en la "Hoja de Parametrización"
  del Excel maestro, NO hardcodeados aquí. Esto permite que el usuario de negocio
  cambie una URL o un umbral sin tocar código ni redeployar nada.

Este módulo es responsable únicamente de la parte de secretos/infraestructura.
La carga de parámetros de negocio vive en src/core/excel_reader.py, porque
requiere haber abierto el Excel primero.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

import sys

def _ruta_env() -> str:
    """
    Cuando el programa está empaquetado (PyInstaller), el .env real vive
    en %APPDATA%\\ACW Informes Legales\\.env (separado de la instalación,
    para que se pueda editar sin reinstalar). En desarrollo, se sigue
    usando el .env local del proyecto, como siempre.
    """
    if getattr(sys, "frozen", False):
        ruta = os.path.join(os.environ.get("APPDATA", ""), "ACW Informes Legales", ".env")
        if os.path.exists(ruta):
            return ruta
    return ".env"  # comportamiento normal en desarrollo

load_dotenv(_ruta_env())

def _requerido(nombre_var: str) -> str:
    valor = os.getenv(nombre_var)
    if not valor:
        raise RuntimeError(
            f"Falta la variable de entorno obligatoria: {nombre_var}. "
            f"Revisa tu archivo .env (usa .env.example como plantilla)."
        )
    return valor

@dataclass(frozen=True)
class InfraConfig:
    captcha_api_key: str
    captcha_provider: str
    captcha_enabled: bool
    ai_summary_api_key: str
    ai_summary_model: str
    ai_summary_enabled: bool
    local_download_dir: str
    log_dir: str
    process_run_user: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    graph_drive_id: str
    graph_excel_item_id: str
    cuenta_onedrive: str

def cargar_infra_config() -> InfraConfig:
    # NOTA: captcha_api_key y ai_summary_api_key usan os.getenv (no _requerido)
    # a propósito - todavía no se han contratado esos servicios. El código que
    # los use debe validar explícitamente que no estén vacíos ANTES de llamarlos,
    # no asumir que _requerido ya lo garantizó.
    return InfraConfig(
        captcha_api_key=os.getenv("CAPTCHA_API_KEY", ""),
        captcha_provider=os.getenv("CAPTCHA_PROVIDER", "2captcha"),
        captcha_enabled=os.getenv("CAPTCHA_ENABLED", "false").strip().lower() == "true",
        ai_summary_api_key=os.getenv("AI_SUMMARY_API_KEY", ""),
        ai_summary_model=os.getenv("AI_SUMMARY_MODEL", ""),
        ai_summary_enabled=os.getenv("AI_SUMMARY_ENABLED", "false").strip().lower() == "true",
        local_download_dir=os.getenv("LOCAL_DOWNLOAD_DIR", "./data/staging"),
        log_dir=os.getenv("LOG_DIR", "./data/logs"),
        process_run_user=os.getenv("PROCESS_RUN_USER", "bot-debida-diligencia"),
        # Graph API - azure_tenant_id/client_id/client_secret ya estan en
        # .env; graph_drive_id/graph_excel_item_id se llenan corriendo
        # tests/prueba_graph_buscar_archivo.py (no se buscan a mano).
        azure_tenant_id=os.getenv("AZURE_TENANT_ID", ""),
        azure_client_id=os.getenv("AZURE_CLIENT_ID", ""),
        azure_client_secret=os.getenv("AZURE_CLIENT_SECRET", ""),
        graph_drive_id=os.getenv("GRAPH_DRIVE_ID", ""),
        graph_excel_item_id=os.getenv("GRAPH_EXCEL_ITEM_ID", ""),
        cuenta_onedrive=os.getenv("CUENTA_ONEDRIVE", "unidadq@enlace.ec"),
    )
