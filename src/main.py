"""
Orquestador principal - ACW PLAFT UAFE.

Lee clientes pendientes del Excel real en OneDrive (GraphAPIWriter),
corre los 18 sitios para cada uno, escribe los resultados de vuelta al
Excel, sube la evidencia a OneDrive, y registra cada intento en el log
de auditoría (data/logs/auditoria_YYYY-MM-DD.jsonl).

REINTENTO PARCIAL (2026-09-03, solicitado por Cumplimiento): si un
cliente ya tiene ESTADO="Completado con pendientes", en la siguiente
corrida SOLO se re-ejecutan los sitios que fallaron antes (leídos de la
columna "SITIOS A REVISAR"), no los 18 completos - los sitios que ya
salieron bien quedan intactos en el Excel, sin re-escribirse.

Usa channel="chrome" en TODO el navegador (no solo Salud) para
simplificar - Chrome real funciona igual de bien para el resto de
sitios, evita manejar 2 instancias de navegador para esta demo.

Cada llamada a un sitio está aislada con try/except - un fallo en un
sitio NUNCA detiene el resto (principio de diseño confirmado).
"""
import os
from datetime import datetime

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from src.core.models import Cliente, TipoPersona, ResultadoConsulta
from src.core.logger import registrar_evento
from src.core.excel_writer import GraphAPIWriter
from src.core.graph_uploader import GraphUploader
from src.core.contador_diario import (
    supero_umbral_advertencia, incrementar_contador_hoy, obtener_contador_hoy,
    UMBRAL_ADVERTENCIA_DIARIO,
)
from src.core.notificaciones import notificar_atencion_manual

from src.scrapers.sitio_funcion_judicial import ScraperFuncionJudicial
from src.scrapers.sitio_fiscalia import ScraperFiscalia
from src.scrapers.sitio_sentenciados import ScraperSentenciados
from src.scrapers.sitio_antecedentes_penales import ScraperAntecedentesPenales
from src.scrapers.sitio_sri import ScraperSRI
from src.scrapers.sitio_sri_deudas import ScraperSRIDeudas
from src.scrapers.sitio_sri_estado_tributario import ScraperSRIEstadoTributario
from src.scrapers.sitio_salud import ScraperSalud
from src.scrapers.sitio_iess import ScraperIESS
from src.scrapers.sitio_scvs_companias import ScraperSCVSCompanias
from src.scrapers.sitio_scvs_personas import ScraperSCVSPersonas
from src.scrapers.sitio_contraloria import ScraperContraloria
from src.scrapers.sitio_municipio_quito import ScraperMunicipioQuito
from src.scrapers.sitio_municipio_cuenca import ScraperMunicipioCuenca
from src.scrapers.sitio_municipio_ambato import ScraperMunicipioAmbato
from src.scrapers.sitio_municipio_esmeraldas import ScraperMunicipioEsmeraldas
from src.scrapers.sitio_municipio_manta import ScraperMunicipioManta
from src.scrapers.sitio_sercop_proveedor import ScraperSERCOPProveedor
from src.scrapers.sitio_sercop_certificados import ScraperSERCOPCertificados
from src.scrapers.cadena_representante import resolver_representante_legal

RUTA_EXCEL_LOCAL = "templates/Matriz Revisión Clientes.xlsx"

try:
    _writer_parametros = GraphAPIWriter(
        cuenta_onedrive=os.getenv("CUENTA_ONEDRIVE", "unidadq@enlace.ec"),
        drive_id=os.getenv("GRAPH_DRIVE_ID"),
        item_id=os.getenv("GRAPH_EXCEL_ITEM_ID"),
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET"),
    )
    _parametros = _writer_parametros.leer_parametrizacion()
except Exception:
    # Este bloque corre al IMPORTAR el modulo, antes de main() - un
    # fallo aqui (credenciales mal configuradas en el .env, sin
    # internet, permisos de Graph, etc.) cerraba la ventana del .exe
    # al instante sin que se pudiera leer nada.
    import traceback
    print(f"\n{'='*70}")
    print("ERROR AL INICIAR - no se pudo conectar con el Excel de OneDrive")
    print(f"{'='*70}\n")
    traceback.print_exc()
    print(f"\n{'='*70}")
    print("Revisa que el archivo .env tenga las credenciales correctas.")
    print(r"Ubicacion: %APPDATA%\Lynx\.env")
    input("\nCopia el error de arriba y presiona ENTER para cerrar...")
    raise SystemExit(1)

_MAPEO_URLS = {
    "funcion_judicial": "URL_FUNCION_JUDICIAL",
    "fiscalia_noticias": "URL_FISCALIA_NOTICIAS",
    "sentenciados": "URL_SENTENCIADOS",
    "antecedentes_penales": "URL_ANTECEDENTES_PENALES",
    "sri_ruc": "URL_SRI_RUC",
    "sri_deudas": "URL_SRI_DEUDAS",
    "sri_estado_tributario": "URL_SRI_ESTADO_TRIBUTARIO",
    "salud": "URL_SALUD",
    "iess": "URL_IESS",
    "scvs_companias": "URL_SCVS_COMPANIAS",
    "scvs_personas": "URL_SCVS_PERSONA",
    "contraloria": "URL_CONTRALORIA",
    "municipio_quito": "URL_MUNICIPIO_QUITO",
    "municipio_cuenca": "URL_MUNICIPIO_CUENCA",
    "municipio_ambato": "URL_MUNICIPIO_AMBATO",
    "municipio_esmeraldas": "URL_MUNICIPIO_ESMERALDAS",
    "municipio_manta": "URL_MUNICIPIO_MANTA",
    "sercop_proveedor": "URL_SERCOP_PROVEEDOR",
    "sercop_certificados": "URL_SERCOP_CERTIFICADOS",
}

_MAPEO_NOMBRES_LEGIBLES = {
    "sri_ruc": "SRI RUC",
    "sri_deudas": "SRI Deudas",
    "sri_estado_tributario": "SRI Estado Tributario",
    "cadena_representante_legal": "Representante Legal",
    "municipio_quito": "Municipio Quito",
    "municipio_cuenca": "Municipio Cuenca",
    "municipio_ambato": "Municipio Ambato",
    "municipio_esmeraldas": "Municipio Esmeraldas",
    "municipio_manta": "Municipio Manta",
    "sercop_proveedor": "SERCOP Proveedor",
    "sercop_certificados": "SERCOP Certificados",
    "salud": "Salud",
    "iess": "IESS",
    "scvs_companias": "SCVS Compañías",
    "scvs_personas": "SCVS Personas",
    "beneficiarios_finales": "Beneficiarios Finales",
    "antecedentes_penales": "Antecedentes Penales",
    "sentenciados": "Sentenciados",
    "funcion_judicial": "Función Judicial",
    "fiscalia": "Fiscalía",
    "contraloria": "Contraloría",
}

# .upper() en ambos lados - "_escribir_valor_con_estilo" convierte TODO
# a mayusculas antes de guardarlo en el Excel, asi que lo que se lee de
# vuelta de "SITIOS A REVISAR" siempre viene en mayusculas
# ("SENTENCIADOS", no "Sentenciados") - sin esto, el reintento parcial
# nunca reconoce ningun nombre de sitio correctamente.
_MAPEO_NOMBRES_INVERSO = {nombre.upper(): clave for clave, nombre in _MAPEO_NOMBRES_LEGIBLES.items()}

_SITIOS_QUE_NECESITAN_PERSONA_RESUELTA = {
    "salud", "iess", "scvs_personas", "antecedentes_penales",
    "contraloria", "sercop_certificados", "scvs_companias", "beneficiarios_finales",
}

_faltantes = [param for param in _MAPEO_URLS.values() if not _parametros.get(param)]
if _faltantes:
    print(f"ERROR: faltan estos parámetros en la Hoja de Parametrización del Excel: {', '.join(_faltantes)}")
    raise SystemExit(1)

URLS = {clave: _parametros[param] for clave, param in _MAPEO_URLS.items()}


def _calcular_ruta_evidencia(cliente: Cliente) -> str:
    ahora = datetime.now()
    return os.path.abspath(os.path.join(
        "data/staging", "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", cliente.identificacion,
    ))


def _parsear_sitios_a_reintentar(texto: str) -> set | None:
    texto = (texto or "").strip()
    if not texto or texto == "-":
        return None

    claves = set()
    for parte in texto.split(" / "):
        nombre_legible = parte.replace(" (SITIO FUERA DE SERVICIO)", "").strip()
        clave = _MAPEO_NOMBRES_INVERSO.get(nombre_legible.upper())
        if clave:
            claves.add(clave)
        else:
            print(f"    [advertencia] no se pudo reconocer '{nombre_legible}' de SITIOS A REVISAR - se ignora esa entrada")

    return claves if claves else None


def procesar_cliente(page, cliente: Cliente, sitios_a_ejecutar=None) -> dict:
    resultados = {}

    def _ejecutar(nombre_paso, funcion, intentos_maximos=2):
        """
        Reintenta automáticamente UNA vez (2 intentos totales) cuando el
        fallo es especificamente un TimeoutError - confirmado que la
        mayoria de sitios gubernamentales de este proyecto son
        intermitentes, no rotos, y un segundo intento desde cero
        (la funcion vuelve a navegar/buscar completo) suele resolverlo.
        Otros tipos de error (captcha, elemento no encontrado, etc.) NO
        se reintentan aqui - esos ya tienen su propio manejo especifico
        en el scraper que corresponda (ej. reintento-con-recarga de
        Contraloria/Antecedentes Penales), o simplemente no se resuelven
        solos con un segundo intento identico.
        """
        if sitios_a_ejecutar is not None and nombre_paso not in sitios_a_ejecutar:
            return

        ultimo_error = None
        for intento in range(1, intentos_maximos + 1):
            try:
                resultados[nombre_paso] = funcion()
                sufijo = f" (tras {intento} intentos)" if intento > 1 else ""
                print(f"[{cliente.identificacion}] OK - {nombre_paso}{sufijo}")
                registrar_evento(
                    cliente_identificacion=cliente.identificacion,
                    cliente_nombre=cliente.nombre_para_mostrar,
                    usuario_proceso="bot-debida-diligencia",
                    resultado=ResultadoConsulta.EXITO,
                    sitio_web=nombre_paso,
                    ruta_evidencia=_calcular_ruta_evidencia(cliente),
                )
                return
            except Exception as e:
                ultimo_error = e
                es_timeout = "Timeout" in type(e).__name__
                if es_timeout and intento < intentos_maximos:
                    print(f"[{cliente.identificacion}] {nombre_paso} - Timeout en intento {intento}/{intentos_maximos}, reintentando...")
                    continue
                break

        resultados[nombre_paso] = {"error": str(ultimo_error), "requiere_revision_manual": True}
        print(f"[{cliente.identificacion}] FALLÓ ({nombre_paso}): {type(ultimo_error).__name__}: {ultimo_error} - marcado para revisión manual")

        texto_error = f"{type(ultimo_error).__name__}: {ultimo_error}"
        if "Timeout" in type(ultimo_error).__name__:
            resultado_log = ResultadoConsulta.TIMEOUT
        elif "captcha" in texto_error.lower():
            resultado_log = ResultadoConsulta.ERROR_CAPTCHA
        else:
            resultado_log = ResultadoConsulta.ERROR_DESCONOCIDO

        registrar_evento(
            cliente_identificacion=cliente.identificacion,
            cliente_nombre=cliente.nombre_para_mostrar,
            usuario_proceso="bot-debida-diligencia",
            resultado=resultado_log,
            sitio_web=nombre_paso,
            detalle=texto_error,
        )

    _ejecutar("sri_ruc", lambda: ScraperSRI(context=page.context, url_base=URLS["sri_ruc"]).consultar_ruc(page, cliente))
    _ejecutar("sri_deudas", lambda: ScraperSRIDeudas(context=page.context, url_base=URLS["sri_deudas"]).consultar_deudas(page, cliente))
    _ejecutar("sri_estado_tributario", lambda: ScraperSRIEstadoTributario(context=page.context, url_base=URLS["sri_estado_tributario"]).consultar_estado_tributario(page, cliente))

    cliente_para_persona = cliente
    ruc_representante = ""
    necesita_representante_legal = (
        cliente.tipo_persona == TipoPersona.JURIDICA
        and (
            sitios_a_ejecutar is None
            or "cadena_representante_legal" in sitios_a_ejecutar
            or bool(sitios_a_ejecutar & _SITIOS_QUE_NECESITAN_PERSONA_RESUELTA)
        )
    )
    if necesita_representante_legal:
        scraper_sri_cadena = ScraperSRI(context=page.context, url_base=URLS["sri_ruc"])
        try:
            cadena = resolver_representante_legal(page, scraper_sri_cadena, cliente)
            if sitios_a_ejecutar is None or "cadena_representante_legal" in sitios_a_ejecutar:
                resultados["cadena_representante_legal"] = cadena
                if not cadena["persona_encontrada"]:
                    resultados["cadena_representante_legal"]["requiere_revision_manual"] = True
                    print(f"[{cliente.identificacion}] ADVERTENCIA: no se resolvió representante legal - {cadena['mensaje']} - marcado para revisión manual")

            if cadena["persona_encontrada"]:
                ruc_representante = cadena["identificacion"]
                cliente_para_persona = Cliente(
                    identificacion=cadena["identificacion"],
                    tipo_persona=TipoPersona.NATURAL,
                    nombres_completos=cadena["nombre"],
                    identificacion_evidencia=cliente.identificacion,
                    subcarpeta_evidencia=f"representante_legal_{cadena['identificacion']}",
                )
                print(f"[{cliente.identificacion}] Representante legal resuelto: {cadena['nombre']} ({cadena['identificacion']})")
        except Exception as e:
            if sitios_a_ejecutar is None or "cadena_representante_legal" in sitios_a_ejecutar:
                resultados["cadena_representante_legal"] = {"error": str(e), "requiere_revision_manual": True}
            print(f"[{cliente.identificacion}] FALLÓ cadena de representante legal: {e}")

    _ejecutar("municipio_quito", lambda: ScraperMunicipioQuito(context=page.context, url_base=URLS["municipio_quito"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_cuenca", lambda: ScraperMunicipioCuenca(context=page.context, url_base=URLS["municipio_cuenca"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_ambato", lambda: ScraperMunicipioAmbato(context=page.context, url_base=URLS["municipio_ambato"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_esmeraldas", lambda: ScraperMunicipioEsmeraldas(context=page.context, url_base=URLS["municipio_esmeraldas"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_manta", lambda: ScraperMunicipioManta(context=page.context, url_base=URLS["municipio_manta"]).buscar_cliente(page, cliente))

    _ejecutar("sercop_proveedor", lambda: ScraperSERCOPProveedor(context=page.context, url_base=URLS["sercop_proveedor"]).buscar_cliente(page, cliente))
    _ejecutar("sercop_certificados", lambda: ScraperSERCOPCertificados(context=page.context, url_base=URLS["sercop_certificados"]).buscar_cliente(page, cliente, ruc_representante_legal=ruc_representante))

    _ejecutar("salud", lambda: ScraperSalud(context=page.context, url_base=URLS["salud"]).buscar_cliente(page, cliente_para_persona))

    _ejecutar("iess", lambda: ScraperIESS(context=page.context, url_base=URLS["iess"]).buscar_cliente(page, cliente_para_persona))

    if cliente.tipo_persona == TipoPersona.JURIDICA:
        _ejecutar("scvs_companias", lambda: ScraperSCVSCompanias(context=page.context, url_base=URLS["scvs_companias"]).buscar_cliente(page, cliente))
        _ejecutar("beneficiarios_finales", lambda: ScraperSCVSCompanias(context=page.context, url_base=URLS["scvs_companias"]).consultar_beneficiarios_finales(page, cliente))
    _ejecutar("scvs_personas", lambda: ScraperSCVSPersonas(context=page.context, url_base=URLS["scvs_personas"], url_base_sri=URLS["sri_ruc"]).buscar_cliente(page, cliente_para_persona))

    _ejecutar("antecedentes_penales", lambda: ScraperAntecedentesPenales(context=page.context, url_base=URLS["antecedentes_penales"]).buscar_cliente(page, cliente_para_persona))

    _ejecutar("sentenciados", lambda: ScraperSentenciados(context=page.context, url_base=URLS["sentenciados"]).buscar_cliente(page, cliente))

    _ejecutar("funcion_judicial", lambda: ScraperFuncionJudicial(context=page.context, url_base=URLS["funcion_judicial"]).buscar_y_procesar_cliente(page, cliente))
    _ejecutar("fiscalia", lambda: ScraperFiscalia(context=page.context, url_base=URLS["fiscalia_noticias"]).buscar_cliente(page, cliente))

    _ejecutar("contraloria", lambda: ScraperContraloria(context=page.context, url_base=URLS["contraloria"]).buscar_cliente(page, cliente_para_persona))

    return resultados


def _fallo(resultado) -> bool:
    """
    True si este resultado necesita revision manual - dos casos:
    1. Fallo total capturado por _ejecutar (dict con
       'requiere_revision_manual') - el caso de siempre.
    2. Resultado REAL obtenido con exito, pero con evidencia incompleta
       (ej. Antecedentes Penales: se obtuvo SI/NO pero el PDF de
       certificado no se pudo descargar) - el objeto tiene su propio
       atributo requiere_revision_manual=True, aunque no sea un dict.
    """
    if isinstance(resultado, dict) and resultado.get("requiere_revision_manual") is True:
        return True
    return getattr(resultado, "requiere_revision_manual", False) is True


def _es_sitio_fuera_de_servicio(texto_error: str) -> bool:
    señales_sitio_caido = [
        "Page.goto", "net::ERR_", "ERR_CONNECTION", "ERR_NAME_NOT_RESOLVED",
        "ERR_TIMED_OUT", "ERR_INTERNET_DISCONNECTED", "ERR_ADDRESS_UNREACHABLE",
    ]
    return any(señal in texto_error for señal in señales_sitio_caido)


def _calcular_sitios_a_revisar(resultados: dict) -> str:
    nombres = []
    for sitio, resultado in resultados.items():
        if not _fallo(resultado):
            continue
        nombre_legible = _MAPEO_NOMBRES_LEGIBLES.get(sitio, sitio)
        texto_error = resultado.get("error", "") if isinstance(resultado, dict) else ""
        if _es_sitio_fuera_de_servicio(texto_error):
            nombres.append(f"{nombre_legible} (Sitio Fuera de Servicio)")
        else:
            nombres.append(nombre_legible)
    return " / ".join(nombres) if nombres else "-"


def escribir_resultados_excel(writer: GraphAPIWriter, cliente: Cliente, resultados: dict) -> None:
    fila = cliente.fila_excel

    if "sri_ruc" in resultados and not _fallo(resultados["sri_ruc"]):
        datos_sri_cliente = dict(resultados["sri_ruc"])
        datos_rl = None
        cadena = resultados.get("cadena_representante_legal")
        if isinstance(cadena, dict) and cadena.get("persona_encontrada"):
            datos_rl = cadena.get("datos_sri_persona") or None
            datos_sri_cliente["representante_legal_nombre"] = cadena["nombre"]
            datos_sri_cliente["representante_legal_identificacion"] = cadena["identificacion"]
        writer.escribir_sri_ruc(fila, datos_sri_cliente, datos_representante_legal=datos_rl)

    if "sri_deudas" in resultados and not _fallo(resultados["sri_deudas"]):
        deuda = resultados["sri_deudas"]
        writer.escribir_sri_deudas(fila, deuda.tiene_deuda_firme, deuda.valor_deuda_firme)

    if "sri_estado_tributario" in resultados and not _fallo(resultados["sri_estado_tributario"]):
        estado_trib = resultados["sri_estado_tributario"]
        writer.escribir_sri_estado_tributario(fila, estado_trib.resultado, estado_trib.obligaciones_pendientes)

    mapeo_municipios = {
        "Quito": "municipio_quito", "Cuenca": "municipio_cuenca", "Ambato": "municipio_ambato",
        "Esmeraldas": "municipio_esmeraldas", "Manta": "municipio_manta",
    }
    resultados_municipios = {
        nombre: resultados[clave] for nombre, clave in mapeo_municipios.items()
        if clave in resultados and not _fallo(resultados[clave])
    }
    if resultados_municipios:
        writer.escribir_municipios(fila, resultados_municipios)

    if "sercop_proveedor" in resultados and not _fallo(resultados["sercop_proveedor"]):
        writer.escribir_sercop_proveedor(fila, resultados["sercop_proveedor"]["estado"])

    if "sercop_certificados" in resultados and not _fallo(resultados["sercop_certificados"]):
        writer.escribir_sercop_certificados(fila, resultados["sercop_certificados"])

    if "salud" in resultados and not _fallo(resultados["salud"]):
        salud = resultados["salud"]
        writer.escribir_salud(fila, salud.situacion_laboral, salud.tipo_afiliacion)

    if "iess" in resultados and not _fallo(resultados["iess"]):
        iess = resultados["iess"]
        writer.escribir_iess(fila, iess.get("iess", ""), iess.get("deuda_obligaciones", ""))

    if "scvs_companias" in resultados and not _fallo(resultados["scvs_companias"]):
        scvs = resultados["scvs_companias"]
        writer.escribir_scvs_companias(fila, scvs.registrado, scvs.cumplimiento_obligaciones)
    elif cliente.tipo_persona == TipoPersona.NATURAL:
        # Natural nunca ejecuta este sitio (SCVS Companias solo aplica a
        # Juridica) - se escribe "-" en gris explicitamente, mismo
        # criterio que Beneficiarios Finales.
        writer.escribir_scvs_companias(fila, registrado=False)

    if "beneficiarios_finales" in resultados and not _fallo(resultados["beneficiarios_finales"]):
        datos_beneficiarios = resultados["beneficiarios_finales"]
        writer.escribir_beneficiarios_finales(fila, datos_beneficiarios["beneficiarios"], total_real=datos_beneficiarios["total"])
    elif cliente.tipo_persona == TipoPersona.NATURAL:
        writer.escribir_beneficiarios_finales(fila, [])

    if "scvs_personas" in resultados and not _fallo(resultados["scvs_personas"]):
        scvs_personas = resultados["scvs_personas"]
        cadena = resultados.get("cadena_representante_legal")
        if isinstance(cadena, dict) and cadena.get("persona_encontrada"):
            nombre_persona_relacionada = cadena["nombre"]
        else:
            nombre_persona_relacionada = cliente.nombres_completos
        writer.escribir_scvs_personas(fila, scvs_personas, nombre_persona_relacionada)
        writer.escribir_empresas_extranjeras(fila, scvs_personas.get("empresas_extranjeras", []), nombre_persona_relacionada)

    if "antecedentes_penales" in resultados and not isinstance(resultados["antecedentes_penales"], dict):
        # No se usa _fallo() aqui a proposito: un resultado con
        # requiere_revision_manual=True (PDF faltante) SI debe
        # escribirse (ya tenemos el dato real), solo un fallo TOTAL
        # (dict, capturado por _ejecutar cuando ni siquiera se pudo
        # extraer el SI/NO) debe omitirse.
        ap = resultados["antecedentes_penales"]
        posee_bool = str(ap.posee_antecedentes).strip().upper() == "SI"
        writer.escribir_antecedentes_penales(fila, posee_bool)

    if "sentenciados" in resultados and not _fallo(resultados["sentenciados"]):
        lista_sentenciados, total_sentenciados = resultados["sentenciados"]
        writer.escribir_sentenciados(fila, total_sentenciados, lista_sentenciados[:3])

    if "funcion_judicial" in resultados and not _fallo(resultados["funcion_judicial"]):
        procesos, total_procesos, tematica_general = resultados["funcion_judicial"]
        writer.escribir_funcion_judicial(fila, procesos, total_procesos, tematica_general)

    if "fiscalia" in resultados and not _fallo(resultados["fiscalia"]):
        denuncias = resultados["fiscalia"]
        scraper_fiscalia_temp = ScraperFiscalia(context=None, url_base="")
        resumen_fiscalia = scraper_fiscalia_temp.resumen_general_por_denuncia(denuncias)
        writer.escribir_fiscalia_resumen_general(fila, resumen_fiscalia)

    if "contraloria" in resultados and not _fallo(resultados["contraloria"]):
        declaraciones = resultados["contraloria"]
        scraper_contraloria_temp = ScraperContraloria(context=None, url_base="")
        resumen_detallado = scraper_contraloria_temp.resumir_declaraciones(declaraciones)
        writer.escribir_contraloria(fila, resumen_detallado)
        resumen_general = scraper_contraloria_temp.resumen_general_por_cargo(declaraciones)
        writer.escribir_contraloria_resumen_general(fila, resumen_general)

    writer.escribir_estado_final(fila, resultados)
    writer.escribir_sitios_a_revisar(fila, _calcular_sitios_a_revisar(resultados))
    # NOTA: escribir_ruta_evidencia() se llama DESPUES de esto, en main(),
    # una vez que la evidencia ya se subio a OneDrive - necesita el link
    # real (webUrl) que solo existe tras la subida, no la ruta local.


def main():
    writer = _writer_parametros
    clientes = writer.leer_clientes_pendientes()
    print(f"Se encontraron {len(clientes)} clientes pendientes en el Excel.\n")

    if not clientes:
        print("No hay clientes pendientes.")
        return

    uploader = GraphUploader(cuenta_onedrive=os.getenv("CUENTA_ONEDRIVE", "unidadq@enlace.ec"), writer=writer)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200, channel="chrome")
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        resumen_final = {}
        # La advertencia de umbral se muestra UNA sola vez por corrida,
        # no en cada cliente - seria ruido inutil en un lote grande.
        ya_se_advirtio_umbral = False
        for cliente in clientes:
            # Antes esto hacia "break" y detenia el lote a medias. Ahora
            # solo advierte (2026-09-11) - el usuario decide si sigue o
            # corta, el programa no lo decide por el.
            if not ya_se_advirtio_umbral and supero_umbral_advertencia():
                ya_se_advirtio_umbral = True
                mensaje_umbral = (
                    f"Ya van {obtener_contador_hoy()} consultas hoy (umbral de aviso: {UMBRAL_ADVERTENCIA_DIARIO}). "
                    "La corrida CONTINÚA, pero con volúmenes altos los portales suelen "
                    "pedir más captchas manuales o bloquear temporalmente."
                )
                print(f"\n{'='*70}")
                print(f"ADVERTENCIA: {mensaje_umbral}")
                print(f"{'='*70}\n")
                notificar_atencion_manual("Lynx - muchas consultas hoy", mensaje_umbral)

            incrementar_contador_hoy()
            momento_inicio_cliente = datetime.now()

            sitios_a_ejecutar = _parsear_sitios_a_reintentar(cliente.sitios_a_revisar_texto)
            if sitios_a_ejecutar is not None:
                nombres_legibles = [_MAPEO_NOMBRES_LEGIBLES.get(s, s) for s in sitios_a_ejecutar]
                print(f"\n{'='*70}")
                print(f"REINTENTO PARCIAL: {cliente.identificacion} - {cliente.nombre_para_mostrar} (consulta {obtener_contador_hoy()} hoy)")
                print(f"Solo se re-ejecutan: {', '.join(nombres_legibles)}")
                print(f"{'='*70}\n")
            else:
                print(f"\n{'='*70}")
                print(f"PROCESANDO CLIENTE: {cliente.identificacion} - {cliente.nombre_para_mostrar} (consulta {obtener_contador_hoy()} hoy)")
                print(f"{'='*70}\n")

            resultados = procesar_cliente(page, cliente, sitios_a_ejecutar=sitios_a_ejecutar)
            resumen_final[cliente.identificacion] = resultados

            try:
                escribir_resultados_excel(writer, cliente, resultados)

                ahora = datetime.now()
                carpeta_cliente = os.path.join("data/staging/DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", cliente.identificacion)
                # En reintento parcial, solo sube lo generado DESDE que
                # arrancó el procesamiento de este cliente en esta
                # corrida - evita re-subir el historial completo cuando
                # solo se re-ejecutó 1 de los 18 sitios.
                subidos = uploader.subir_carpeta_cliente(
                    carpeta_cliente, cliente.identificacion, str(ahora.year), f"{ahora.month:02d}",
                    modificados_desde=(momento_inicio_cliente if sitios_a_ejecutar is not None else None),
                )
                print(f"[{cliente.identificacion}] {len(subidos)} archivo(s) de evidencia subidos a OneDrive.")

                if subidos:
                    link_carpeta = uploader.obtener_link_carpeta_cliente(cliente.identificacion, str(ahora.year), f"{ahora.month:02d}")
                    writer.escribir_ruta_evidencia(cliente.fila_excel, link_carpeta or _calcular_ruta_evidencia(cliente))
                else:
                    writer.escribir_ruta_evidencia(cliente.fila_excel, _calcular_ruta_evidencia(cliente))

                writer.guardar()
                print(f"[{cliente.identificacion}] Excel actualizado y guardado.")
            except Exception as e:
                print(f"[{cliente.identificacion}] FALLÓ al escribir en Excel o subir evidencia: {type(e).__name__}: {e}")

        print(f"\n{'='*70}")
        print("RESUMEN FINAL")
        print(f"{'='*70}")
        for identificacion, resultados in resumen_final.items():
            print(f"\nCliente {identificacion}:")
            for sitio, resultado in resultados.items():
                estado = "REVISIÓN MANUAL" if _fallo(resultado) else "OK"
                print(f"  {sitio}: {estado}")

        input("\nPresiona ENTER para cerrar...")
        browser.close()


if __name__ == "__main__":
    # Envoltura para que CUALQUIER error inesperado quede visible antes
    # de que la ventana se cierre - critico al correr como .exe
    # empaquetado, donde no hay terminal que sobreviva al proceso
    # (confirmado con evidencia real 2026-09-10: en otra maquina fallaba
    # y era imposible leer el error, la ventana se cerraba al instante).
    # El input() que ya existe al final de main() solo cubre el caso
    # EXITOSO - este cubre los fallos.
    try:
        main()
    except SystemExit:
        raise  # salida intencional (ej. faltan parametros) - ya imprimio su propio mensaje
    except Exception:
        import traceback
        print(f"\n{'='*70}")
        print("ERROR INESPERADO - el programa se detuvo")
        print(f"{'='*70}\n")
        traceback.print_exc()
        print(f"\n{'='*70}")
        input("Copia el error de arriba y presiona ENTER para cerrar...")
        raise