"""
Orquestador principal - ACW PLAFT UAFE.

Lee clientes pendientes del Excel real (LocalExcelWriter por ahora -
cuando se decida pasar a produccion, GraphAPIWriter implementa la
misma interfaz ExcelWriter, es un cambio de una linea), corre los 18
sitios para cada uno, escribe los resultados de vuelta al Excel, y
marca el ESTADO final.

Usa channel="chrome" en TODO el navegador (no solo Salud) para
simplificar - Chrome real funciona igual de bien para el resto de
sitios, evita manejar 2 instancias de navegador para esta demo.

Cada llamada a un sitio está aislada con try/except - un fallo en un
sitio NUNCA detiene el resto (principio de diseño confirmado).
"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from src.core.models import Cliente, TipoPersona
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
from src.core.excel_writer import LocalExcelWriter
from src.core.contador_diario import limite_alcanzado, incrementar_contador_hoy, obtener_contador_hoy
from src.core.excel_writer import GraphAPIWriter
from src.core.graph_uploader import GraphUploader
from datetime import datetime
import os

RUTA_EXCEL_LOCAL = "templates/Matriz Revisión Clientes.xlsx"

# Todas las URLs vienen de la Hoja de Parametrizacion, sin fallback
# hardcodeado (mismo criterio que el proyecto hermano): si falta algun
# parametro, el programa se detiene con un error claro en vez de seguir
# corriendo en silencio contra una URL vieja/desactualizada.
import os
_writer_parametros = GraphAPIWriter(
    cuenta_onedrive=os.getenv("CUENTA_ONEDRIVE", "unidadq@enlace.ec"),
    drive_id=os.getenv("GRAPH_DRIVE_ID"),
    item_id=os.getenv("GRAPH_EXCEL_ITEM_ID"),
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET"),
)
_parametros = _writer_parametros.leer_parametrizacion()

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
    "antecedentes_penales": "Antecedentes Penales",
    "sentenciados": "Sentenciados",
    "funcion_judicial": "Función Judicial",
    "fiscalia": "Fiscalía",
    "contraloria": "Contraloría",
}

_faltantes = [param for param in _MAPEO_URLS.values() if not _parametros.get(param)]
if _faltantes:
    print(f"ERROR: faltan estos parámetros en la Hoja de Parametrización del Excel: {', '.join(_faltantes)}")
    raise SystemExit(1)

URLS = {clave: _parametros[param] for clave, param in _MAPEO_URLS.items()}


def procesar_cliente(page, cliente: Cliente) -> dict:
    resultados = {}

    def _ejecutar(nombre_paso, funcion):
        try:
            resultados[nombre_paso] = funcion()
            print(f"[{cliente.identificacion}] OK - {nombre_paso}")
        except Exception as e:
            resultados[nombre_paso] = {"error": str(e), "requiere_revision_manual": True}
            print(f"[{cliente.identificacion}] FALLÓ ({nombre_paso}): {type(e).__name__}: {e} - marcado para revisión manual")

    # --- 1. SRI (siempre el cliente mismo) ---
    _ejecutar("sri_ruc", lambda: ScraperSRI(context=page.context, url_base=URLS["sri_ruc"]).consultar_ruc(page, cliente))
    _ejecutar("sri_deudas", lambda: ScraperSRIDeudas(context=page.context, url_base=URLS["sri_deudas"]).consultar_deudas(page, cliente))
    _ejecutar("sri_estado_tributario", lambda: ScraperSRIEstadoTributario(context=page.context, url_base=URLS["sri_estado_tributario"]).consultar_estado_tributario(page, cliente))

    # --- Resolver representante legal SI es Jurídica (necesario antes de
    # Salud/IESS/Contraloría/SERCOP-certificados, que vienen después) ---
    cliente_para_persona = cliente
    ruc_representante = ""
    if cliente.tipo_persona == TipoPersona.JURIDICA:
        scraper_sri_cadena = ScraperSRI(context=page.context, url_base=URLS["sri_ruc"])
        try:
            cadena = resolver_representante_legal(page, scraper_sri_cadena, cliente)
            resultados["cadena_representante_legal"] = cadena
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
            else:
                # No resolver el RL es un caso real de revision manual -
                # sin esto, quedaba marcado "OK" en el resumen/Excel aunque
                # nunca se pudo verificar quien es el representante legal.
                resultados["cadena_representante_legal"]["requiere_revision_manual"] = True
                print(f"[{cliente.identificacion}] ADVERTENCIA: no se resolvió representante legal - {cadena['mensaje']} - marcado para revisión manual")
        except Exception as e:
            resultados["cadena_representante_legal"] = {"error": str(e), "requiere_revision_manual": True}
            print(f"[{cliente.identificacion}] FALLÓ cadena de representante legal: {e}")

    # --- 2. Municipios (siempre el cliente mismo) ---
    _ejecutar("municipio_quito", lambda: ScraperMunicipioQuito(context=page.context, url_base=URLS["municipio_quito"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_cuenca", lambda: ScraperMunicipioCuenca(context=page.context, url_base=URLS["municipio_cuenca"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_ambato", lambda: ScraperMunicipioAmbato(context=page.context, url_base=URLS["municipio_ambato"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_esmeraldas", lambda: ScraperMunicipioEsmeraldas(context=page.context, url_base=URLS["municipio_esmeraldas"]).buscar_cliente(page, cliente))
    _ejecutar("municipio_manta", lambda: ScraperMunicipioManta(context=page.context, url_base=URLS["municipio_manta"]).buscar_cliente(page, cliente))

    # --- 3. SERCOP / INCOP ---
    _ejecutar("sercop_proveedor", lambda: ScraperSERCOPProveedor(context=page.context, url_base=URLS["sercop_proveedor"]).buscar_cliente(page, cliente))
    _ejecutar("sercop_certificados", lambda: ScraperSERCOPCertificados(context=page.context, url_base=URLS["sercop_certificados"]).buscar_cliente(page, cliente, ruc_representante_legal=ruc_representante))

    # --- 4. Salud (persona: cliente o representante) ---
    _ejecutar("salud", lambda: ScraperSalud(context=page.context, url_base=URLS["salud"]).buscar_cliente(page, cliente_para_persona))

    # --- 5. IESS (persona: cliente o representante) ---
    _ejecutar("iess", lambda: ScraperIESS(context=page.context, url_base=URLS["iess"]).buscar_cliente(page, cliente_para_persona))

    # --- 6. SCVS - Compañías (solo Jurídica) y Personas (persona: cliente o representante) ---
    if cliente.tipo_persona == TipoPersona.JURIDICA:
        _ejecutar("scvs_companias", lambda: ScraperSCVSCompanias(context=page.context, url_base=URLS["scvs_companias"]).buscar_cliente(page, cliente))
    _ejecutar("scvs_personas", lambda: ScraperSCVSPersonas(context=page.context, url_base=URLS["scvs_personas"], url_base_sri=URLS["sri_ruc"]).buscar_cliente(page, cliente_para_persona))
    
    # --- 7. Antecedentes Penales (persona: cliente o representante) ---
    _ejecutar("antecedentes_penales", lambda: ScraperAntecedentesPenales(context=page.context, url_base=URLS["antecedentes_penales"]).buscar_cliente(page, cliente_para_persona))

    # --- 8. Sentenciados ---
    _ejecutar("sentenciados", lambda: ScraperSentenciados(context=page.context, url_base=URLS["sentenciados"]).buscar_cliente(page, cliente))

    # --- 9. Función Judicial (incluye Fiscalía dentro del mismo Sitio 8) ---
    _ejecutar("funcion_judicial", lambda: ScraperFuncionJudicial(context=page.context, url_base=URLS["funcion_judicial"]).buscar_y_procesar_cliente(page, cliente))
    _ejecutar("fiscalia", lambda: ScraperFiscalia(context=page.context, url_base=URLS["fiscalia_noticias"]).buscar_cliente(page, cliente))

    # --- 10. Contraloría (persona: cliente o representante) ---
    _ejecutar("contraloria", lambda: ScraperContraloria(context=page.context, url_base=URLS["contraloria"]).buscar_cliente(page, cliente_para_persona))

    return resultados


def _fallo(resultado) -> bool:
    """True si este resultado es un error capturado por _ejecutar (dict
    con 'requiere_revision_manual'), no un resultado real del sitio."""
    return isinstance(resultado, dict) and resultado.get("requiere_revision_manual") is True

def _calcular_sitios_a_revisar(resultados: dict) -> str:
    nombres = [
        _MAPEO_NOMBRES_LEGIBLES.get(sitio, sitio)
        for sitio, resultado in resultados.items()
        if _fallo(resultado)
    ]
    return " / ".join(nombres) if nombres else "-"

def _calcular_ruta_evidencia(cliente: Cliente) -> str:
    """Misma logica de carpeta que ya usan capturar_evidencia()/
    guardar_pdf_local() - carpeta raiz de este cliente, sin el
    subdirectorio de cada sitio."""
    ahora = datetime.now()
    return os.path.abspath(os.path.join(
        "data/staging", "DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", cliente.identificacion,
    ))

def escribir_resultados_excel(writer: LocalExcelWriter, cliente: Cliente, resultados: dict) -> None:
    """
    Traduce el diccionario crudo de resultados (tal como lo arma
    procesar_cliente) a las llamadas escribir_* correspondientes. Un
    sitio que falló (ver _fallo) se salta - no hay datos reales que
    escribir para ese sitio, y el ESTADO final ya lo refleja.
    """
    fila = cliente.fila_excel

    if not _fallo(resultados.get("sri_ruc")):
        datos_sri_cliente = dict(resultados["sri_ruc"])  # copia, no mutar el original
        datos_rl = None
        cadena = resultados.get("cadena_representante_legal")
        if isinstance(cadena, dict) and cadena.get("persona_encontrada"):
            datos_rl = cadena.get("datos_sri_persona") or None
            # Las columnas H/I ("Representante Legal"/"ID Representante
            # Legal") deben reflejar el RESULTADO FINAL de la cadena, no
            # el representante directo de la consulta SRI propia del
            # cliente - si la cadena tiene 2+ niveles, esos dos datos
            # son distintos (uno es una entidad intermedia, el otro la
            # persona real). Confirmado con evidencia real: AMBACAR
            # mostraba una empresa intermedia en H/I mientras el bloque
            # SRI-RL (22-29) ya mostraba correctamente a la persona final.
            datos_sri_cliente["representante_legal_nombre"] = cadena["nombre"]
            datos_sri_cliente["representante_legal_identificacion"] = cadena["identificacion"]
        writer.escribir_sri_ruc(fila, datos_sri_cliente, datos_representante_legal=datos_rl)

    if not _fallo(resultados.get("sri_deudas")):
        deuda = resultados["sri_deudas"]
        writer.escribir_sri_deudas(fila, deuda.tiene_deuda_firme, deuda.valor_deuda_firme)

    if not _fallo(resultados.get("sri_estado_tributario")):
        estado_trib = resultados["sri_estado_tributario"]
        writer.escribir_sri_estado_tributario(fila, estado_trib.resultado, estado_trib.obligaciones_pendientes)

    # Municipios: se consolidan los 5 en una sola llamada. Si alguno
    # falló individualmente, se omite del dict (escribir_municipios ya
    # maneja bien un dict con menos de 5 entradas).
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

    if not _fallo(resultados.get("sercop_proveedor")):
        writer.escribir_sercop_proveedor(fila, resultados["sercop_proveedor"]["estado"])

    if not _fallo(resultados.get("sercop_certificados")):
        writer.escribir_sercop_certificados(fila, resultados["sercop_certificados"])

    if not _fallo(resultados.get("salud")):
        salud = resultados["salud"]
        writer.escribir_salud(fila, salud.situacion_laboral, salud.tipo_afiliacion)

    if not _fallo(resultados.get("iess")):
        iess = resultados["iess"]
        writer.escribir_iess(fila, iess.get("iess", ""), iess.get("deuda_obligaciones", ""))

    if "scvs_companias" in resultados and not _fallo(resultados["scvs_companias"]):
        scvs = resultados["scvs_companias"]
        writer.escribir_scvs_companias(fila, scvs.registrado, scvs.cumplimiento_obligaciones)

    if not _fallo(resultados.get("antecedentes_penales")):
        ap = resultados["antecedentes_penales"]
        posee_bool = str(ap.posee_antecedentes).strip().upper() == "SI"
        writer.escribir_antecedentes_penales(fila, posee_bool)

    if not _fallo(resultados.get("sentenciados")):
        lista_sentenciados, total_sentenciados = resultados["sentenciados"]
        writer.escribir_sentenciados(fila, total_sentenciados, lista_sentenciados[:3])

    if not _fallo(resultados.get("funcion_judicial")):
        procesos, total_procesos, tematica_general = resultados["funcion_judicial"]
        writer.escribir_funcion_judicial(fila, procesos, total_procesos, tematica_general)

    if not _fallo(resultados.get("fiscalia")):
        denuncias = resultados["fiscalia"]
        scraper_fiscalia_temp = ScraperFiscalia(context=None, url_base="")
        resumen_fiscalia = scraper_fiscalia_temp.resumen_general_por_denuncia(denuncias)
        writer.escribir_fiscalia_resumen_general(fila, resumen_fiscalia)

    if not _fallo(resultados.get("contraloria")):
        declaraciones = resultados["contraloria"]
        scraper_contraloria_temp = ScraperContraloria(context=None, url_base="")
        resumen_detallado = scraper_contraloria_temp.resumir_declaraciones(declaraciones)
        writer.escribir_contraloria(fila, resumen_detallado)
        resumen_general = scraper_contraloria_temp.resumen_general_por_cargo(declaraciones)
        writer.escribir_contraloria_resumen_general(fila, resumen_general)

    writer.escribir_estado_final(fila, resultados)
    writer.escribir_sitios_a_revisar(fila, _calcular_sitios_a_revisar(resultados))
    writer.escribir_ruta_evidencia(fila, _calcular_ruta_evidencia(cliente))


def main():
    writer = _writer_parametros  # reutiliza la sesión de Graph ya abierta arriba
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
        for cliente in clientes:
            if limite_alcanzado():
                print("\nHA ALCANZADO EL LIMITE DE CONSULTAS DIARIO")
                break

            incrementar_contador_hoy()
            print(f"\n{'='*70}")
            print(f"PROCESANDO CLIENTE: {cliente.identificacion} - {cliente.nombre_para_mostrar} (consulta {obtener_contador_hoy()}/100 hoy)")
            print(f"{'='*70}\n")

            resultados = procesar_cliente(page, cliente)
            resumen_final[cliente.identificacion] = resultados

            try:
                escribir_resultados_excel(writer, cliente, resultados)
                writer.guardar()
                print(f"[{cliente.identificacion}] Excel actualizado y guardado.")

                ahora = datetime.now()
                carpeta_cliente = os.path.join("data/staging/DebidaDiligencia", str(ahora.year), f"{ahora.month:02d}", cliente.identificacion)
                subidos = uploader.subir_carpeta_cliente(carpeta_cliente, cliente.identificacion, str(ahora.year), f"{ahora.month:02d}")
                print(f"[{cliente.identificacion}] {len(subidos)} archivo(s) de evidencia subidos a OneDrive.")
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

        writer.guardar()  # cierra la sesión de Graph API
        input("\nPresiona ENTER para cerrar...")
        browser.close()


if __name__ == "__main__":
    main()