"""
Resuelve la cadena de representante legal: consulta el SRI de la empresa,
extrae su representante legal, y determina si ya es una persona natural
o si hay que seguir la cadena - hasta un máximo de 3 niveles, con
detección de ciclos.

CLASIFICACIÓN POR TERCER DÍGITO DEL RUC (convención SRI):
- 3er dígito 0-5: persona natural (los primeros 10 dígitos son su
  cédula real, aunque el RUC completo tenga 13) - LA CADENA TERMINA.
- 3er dígito 6: entidad pública - la cadena SIGUE (se consulta esa
  entidad en SRI también).
- 3er dígito 9: empresa privada - la cadena SIGUE.
"""
from playwright.sync_api import Page

from src.core.models import Cliente, TipoPersona
from src.scrapers.sitio_sri import ScraperSRI

MAX_NIVELES = 3


def _clasificar_identificacion(identificacion: str) -> str:
    """
    Devuelve: "persona_natural", "empresa_privada", "entidad_publica",
    o "desconocido" (identificación con formato inesperado).
    """
    identificacion = identificacion.strip()

    if len(identificacion) == 10:
        return "persona_natural"

    if len(identificacion) == 13:
        tercer_digito = identificacion[2]
        if tercer_digito in "012345":
            return "persona_natural"  # RUC de persona natural con negocio propio
        elif tercer_digito == "6":
            return "entidad_publica"
        elif tercer_digito == "9":
            return "empresa_privada"

    return "desconocido"


def resolver_representante_legal(page: Page, scraper_sri: ScraperSRI, cliente_juridica: Cliente) -> dict:
    """
    Devuelve un diccionario con:
    - persona_encontrada: bool
    - nombre: str
    - identificacion: str (cédula real, primeros 10 dígitos si el
      representante tenía RUC de persona natural)
    - cadena: list[dict] - registro de cada nivel consultado, para
      trazabilidad/auditoría
    - mensaje: str - explicación si no se resolvió
    """
    identificaciones_visitadas = set()
    ruc_actual = cliente_juridica.identificacion
    razon_social_actual = cliente_juridica.razon_social
    cadena = []

    for nivel in range(1, MAX_NIVELES + 1):
        if ruc_actual in identificaciones_visitadas:
            return {
                "persona_encontrada": False,
                "nombre": "",
                "identificacion": "",
                "cadena": cadena,
                "mensaje": f"Ciclo detectado en la cadena de representantes (RUC {ruc_actual} ya visitado) - requiere revisión manual.",
            }
        identificaciones_visitadas.add(ruc_actual)

        cliente_temporal = Cliente(
            identificacion=ruc_actual,
            tipo_persona=TipoPersona.JURIDICA,
            razon_social=razon_social_actual,
        )
        datos = scraper_sri.consultar_ruc(page, cliente_temporal)

        id_representante = datos.get("representante_legal_identificacion", "").strip()
        nombre_representante = datos.get("representante_legal_nombre", "")

        clasificacion = _clasificar_identificacion(id_representante) if id_representante else "desconocido"

        cadena.append({
            "nivel": nivel,
            "ruc_consultado": ruc_actual,
            "razon_social": datos.get("razon_social") or razon_social_actual,
            "representante_legal_nombre": nombre_representante,
            "representante_legal_identificacion": id_representante,
            "clasificacion": clasificacion,
        })

        if clasificacion == "desconocido":
            return {
                "persona_encontrada": False,
                "nombre": "",
                "identificacion": "",
                "cadena": cadena,
                "mensaje": f"No se pudo extraer/clasificar representante legal en el nivel {nivel} - requiere revisión manual.",
            }

        if clasificacion == "persona_natural":
            cedula_persona = id_representante[:10]

            # Consulta el SRI de la persona misma (no solo sabemos su
            # nombre por ser representante legal - necesitamos SUS
            # PROPIOS datos: razón social, estado, actividad económica,
            # etc., para el bloque espejo de columnas "Representante
            # Legal" en la matriz).
            datos_sri_persona = {}
            try:
                cliente_persona = Cliente(
                    identificacion=cedula_persona,
                    tipo_persona=TipoPersona.NATURAL,
                    nombres_completos=nombre_representante,
                )
                datos_sri_persona = scraper_sri.consultar_ruc(page, cliente_persona)
            except Exception as e:
                print(f"    [advertencia] falló consulta SRI del representante legal: {e}")

            return {
                "persona_encontrada": True,
                "nombre": nombre_representante,
                "identificacion": cedula_persona,
                "cadena": cadena,
                "datos_sri_persona": datos_sri_persona,
                "mensaje": "",
            }

        # empresa_privada o entidad_publica: seguir la cadena
        ruc_actual = id_representante
        razon_social_actual = nombre_representante

    return {
        "persona_encontrada": False,
        "nombre": "",
        "identificacion": "",
        "cadena": cadena,
        "mensaje": f"Se alcanzó el límite de {MAX_NIVELES} niveles sin llegar a una persona natural - requiere revisión manual.",
    }