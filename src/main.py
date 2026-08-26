"""
src/main.py

Orquestador principal - ACW PLAFT UAFE.

ESTADO: demo con clientes de prueba fijos (Diego, INDUAUTO), sin
conexión a Excel real todavía (pendiente de integrar Graph API con el
mapeo de 179 columnas ya confirmado con cumplimiento).

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
from src.scrapers.sitio_contraloria import ScraperContraloria
from src.scrapers.sitio_municipio_quito import ScraperMunicipioQuito
from src.scrapers.sitio_municipio_cuenca import ScraperMunicipioCuenca
from src.scrapers.sitio_municipio_ambato import ScraperMunicipioAmbato
from src.scrapers.sitio_municipio_esmeraldas import ScraperMunicipioEsmeraldas
from src.scrapers.sitio_municipio_manta import ScraperMunicipioManta
from src.scrapers.sitio_sercop_proveedor import ScraperSERCOPProveedor
from src.scrapers.sitio_sercop_certificados import ScraperSERCOPCertificados
from src.scrapers.cadena_representante import resolver_representante_legal


URLS = {
    "funcion_judicial": "https://consultas.funcionjudicial.gob.ec/informacionjudicial/public/informacion.jsf",
    "fiscalia_totem": "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/",
    "fiscalia_noticias": "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/noticiasdelito/index.php",
    "sentenciados": "https://consultas.funcionjudicial.gob.ec/informacionjudicialindividual/pages/index.jsf#!/",
    "antecedentes_penales": "https://certificados.ministeriodelinterior.gob.ec/gestorcertificados/antecedentes/",
    "sri_ruc": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
    "sri_deudas": "https://srienlinea.sri.gob.ec/sri-en-linea/SriPagosWeb/ConsultaDeudasFirmesImpugnadas/Consultas/consultaDeudasFirmesImpugnadas",
    "sri_estado_tributario": "https://srienlinea.sri.gob.ec/sri-en-linea/SriDeclaracionesWeb/EstadoTributario/Consultas/consultaEstadoTributario",
    "salud": "https://coberturasalud.msp.gob.ec/",
    "iess": "https://www.iess.gob.ec/empleador-web/pages/morapatronal/certificadoCumplimientoPublico.jsf",
    "scvs_companias": "https://appscvsgen.supercias.gob.ec/consultaCompanias/societario/busquedaCompanias.jsf",
    "contraloria": "https://www.contraloria.gob.ec/Consultas/DeclaracionesJuradas",
    "municipio_quito": "https://pago.quito.gob.ec/",
    "municipio_cuenca": "https://enlinea.cuenca.gob.ec/#/impuestos",
    "municipio_ambato": "https://gadmaapps.ambato.gob.ec:9001/apex/f?p=102:9:2530006028746:::9::",
    "municipio_esmeraldas": "https://consulta.esmeraldas.gob.ec/index.jsp",
    "municipio_manta": "https://portalciudadano.manta.gob.ec/consulta",
    "sercop_proveedor": "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/EP/BusquedaProveedorCpc.cpe",
    "sercop_certificados": "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/FO/formularioCertificados.cpe",
}

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

    # --- 6. SCVS - Compañías (activo). Personas se agrega aquí cuando esté listo ---
    if cliente.tipo_persona == TipoPersona.JURIDICA:
        _ejecutar("scvs_companias", lambda: ScraperSCVSCompanias(context=page.context, url_base=URLS["scvs_companias"]).buscar_cliente(page, cliente))
    # TODO: agregar scvs_personas aquí cuando el scraper esté listo

    # --- 7. Antecedentes Penales (persona: cliente o representante) ---
    _ejecutar("antecedentes_penales", lambda: ScraperAntecedentesPenales(context=page.context, url_base=URLS["antecedentes_penales"]).buscar_cliente(page, cliente_para_persona))

    # --- 8. Sentenciados ---
    _ejecutar("sentenciados", lambda: ScraperSentenciados(context=page.context, url_base=URLS["sentenciados"]).buscar_cliente(page, cliente))

    # --- 9. Función Judicial (incluye Fiscalía dentro del mismo Sitio 8) ---
    _ejecutar("funcion_judicial", lambda: ScraperFuncionJudicial(context=page.context, url_base=URLS["funcion_judicial"]).buscar_y_procesar_cliente(page, cliente))
    _ejecutar("fiscalia", lambda: ScraperFiscalia(context=page.context, url_base=URLS["fiscalia_noticias"], url_base_totem=URLS["fiscalia_totem"]).buscar_cliente(page, cliente))

    # --- 10. Contraloría (persona: cliente o representante) ---
    _ejecutar("contraloria", lambda: ScraperContraloria(context=page.context, url_base=URLS["contraloria"]).buscar_cliente(page, cliente_para_persona))

    return resultados

def main():
    clientes_prueba = [
        #Cliente(identificacion="1001322518", tipo_persona=TipoPersona.NATURAL, nombres_completos="Torres Gordillo Diego Patricio"),
        Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A."),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200, channel="chrome")
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        resumen_final = {}
        for cliente in clientes_prueba:
            print(f"\n{'='*70}")
            print(f"PROCESANDO CLIENTE: {cliente.identificacion} - {cliente.nombre_para_mostrar}")
            print(f"{'='*70}\n")
            resumen_final[cliente.identificacion] = procesar_cliente(page, cliente)

        print(f"\n{'='*70}")
        print("RESUMEN FINAL")
        print(f"{'='*70}")
        for identificacion, resultados in resumen_final.items():
            print(f"\nCliente {identificacion}:")
            for sitio, resultado in resultados.items():
                estado = "REVISIÓN MANUAL" if isinstance(resultado, dict) and resultado.get("requiere_revision_manual") else "OK"
                print(f"  {sitio}: {estado}")

        input("\nPresiona ENTER para cerrar...")
        browser.close()


if __name__ == "__main__":
    main()