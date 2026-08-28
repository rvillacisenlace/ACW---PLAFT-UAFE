from src.core.excel_writer import LocalExcelWriter

writer = LocalExcelWriter("templates/Matriz Revisión Clientes.xlsx")

clientes = writer.leer_clientes_pendientes()
print(f"\nTotal clientes pendientes: {len(clientes)}\n")

for c in clientes:
    print(f"Fila {c.fila_excel}: {c.identificacion} | {c.tipo_persona} | {c.nombres_completos or c.razon_social}")

parametros = writer.leer_parametrizacion()
print(f"\nTotal parámetros: {len(parametros)}")
print("URL_ANTECEDENTES_PENALES:", parametros.get("URL_ANTECEDENTES_PENALES"))

# Prueba de escritura - OJO: esto SÍ modifica el archivo real al guardar.
# Comenta las siguientes 2 líneas si solo quieres probar lectura primero.
# writer.escribir_antecedentes_penales(fila_excel=clientes[0].fila_excel, posee_antecedentes=False)
# --- Prueba aislada: escribir_sri_ruc ---
datos_sri_ejemplo = {
    "razon_social": "TORRES GORDILLO DIEGO PATRICIO",
    "estado_contribuyente": "ACTIVO",
    "fecha_inicio_actividades": "01/01/2015",
    "fecha_cese_actividades": "",
    "fecha_reinicio_actividades": "",
    "contribuyente_fantasma": "NO",
    "contribuyente_transacciones_inexistentes": "NO",
    "actividad_economica": "ACTIVIDADES DE CONSULTORIA",
    "representante_legal_nombre": "",
    "representante_legal_identificacion": "",
    "direccion_matriz": "QUITO - PICHINCHA",
}

writer.escribir_sri_ruc(fila_excel=4, datos=datos_sri_ejemplo, datos_representante_legal=None)
writer.guardar()
print("\nescribir_sri_ruc probado - revisa el Excel fila 4, columnas N-U + H/I/F + G")

# --- Prueba aislada: escribir_sri_deudas y escribir_sri_estado_tributario ---
writer.escribir_sri_deudas(fila_excel=4, tiene_deuda_firme=False)
writer.escribir_sri_deudas(fila_excel=5, tiene_deuda_firme=True, valor_deuda_firme="$150.00")
writer.escribir_sri_estado_tributario(fila_excel=4, resultado="AL DIA EN SUS OBLIGACIONES")
writer.escribir_sri_estado_tributario(fila_excel=5, resultado="Pendiente", obligaciones_pendientes="2011 DECLARACION DE IVA MAYO 2026 / 2012 DECLARACION DE IVA JUNIO 2026")
writer.guardar()
print("\nescribir_sri_deudas y escribir_sri_estado_tributario probados - revisa filas 4 y 5, columnas AD y AE")

# --- Prueba aislada: escribir_municipios ---
from src.core.models import DeudaMunicipal

resultados_ejemplo = {
    "Quito": DeudaMunicipal(tiene_deuda=True, valor_total="$15.00", registrado=True),
    "Cuenca": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=True),
    "Ambato": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Esmeraldas": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Manta": DeudaMunicipal(tiene_deuda=True, valor_total="$37.63", registrado=True),
}
writer.escribir_municipios(fila_excel=4, resultados=resultados_ejemplo)

# Caso borde: no registrado en ninguno
resultados_sin_registro = {
    "Quito": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Cuenca": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Ambato": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Esmeraldas": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Manta": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
}
writer.escribir_municipios(fila_excel=5, resultados=resultados_sin_registro)

writer.guardar()
print("\nescribir_municipios probado - revisa filas 4 y 5, columnas AF y AG")

writer.escribir_sercop_proveedor(fila_excel=4, estado="PROVEEDOR DEL ESTADO")
writer.escribir_sercop_proveedor(fila_excel=5, estado="NO ES PROVEEDOR DEL ESTADO")
writer.guardar()
print("\nescribir_sercop_proveedor probado - revisa filas 4 y 5, columna AH")

writer.escribir_sercop_certificados(fila_excel=4, datos={
    "contratos_pendientes": {"resultado": "NO"},
    "incumplimientos": {"resultado": "NO"},
})
writer.escribir_sercop_certificados(fila_excel=5, datos={
    "contratos_pendientes": {"resultado": "SI"},
    "incumplimientos": {"resultado": "INDETERMINADO"},
})
writer.guardar()
print("\nescribir_sercop_certificados probado - revisa filas 4/5, columnas AI y AJ")

writer.escribir_salud(fila_excel=4, situacion_laboral="Relación de Dependencia (IESS)", tipo_afiliacion="Voluntario")
writer.escribir_salud(fila_excel=5, situacion_laboral="", tipo_afiliacion="")
writer.guardar()
print("\nescribir_salud probado - revisa filas 4/5, columnas AL y AM")

writer.escribir_iess(fila_excel=4, iess="NO registra obligaciones patronales en mora", deuda_obligaciones="")
writer.escribir_iess(fila_excel=5, iess="SI registra obligaciones patronales en mora", deuda_obligaciones="1,250.00")
writer.guardar()
print("\nescribir_iess probado - revisa filas 4/5, columnas AN y AO (fila 4 deberia decir '0' en AO)")

writer.escribir_scvs_companias(fila_excel=4, registrado=True, cumplimiento_obligaciones="SI HA CUMPLIDO")
writer.escribir_scvs_companias(fila_excel=5, registrado=True, cumplimiento_obligaciones="NO HA CUMPLIDO")
writer.escribir_scvs_companias(fila_excel=6, registrado=False, cumplimiento_obligaciones="")
writer.guardar()
print("\nescribir_scvs_companias probado - revisa filas 4/5/6, columna AR")

# --- Prueba aislada: escribir_contraloria ---
resumen_ejemplo = {
    "posee_declaraciones": "SI",
    "vigencia": "ALCALDE - GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DE GUAYAQUIL / ALCALDE DE GUAYAQUIL - M.I. MUNICIPIO DE GUAYAQUIL",
    "cargo": "ALCALDE - GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DE GUAYAQUIL",
    "tiempo": "2",
    "ultimo_anio_en_cargo": "2025",
}
writer.escribir_contraloria(fila_excel=4, resumen=resumen_ejemplo)

resumen_desactualizado = {
    "posee_declaraciones": "SI",
    "vigencia": "Desactualizado",
    "cargo": "-",
    "tiempo": "-",
    "ultimo_anio_en_cargo": "-",
}
writer.escribir_contraloria(fila_excel=5, resumen=resumen_desactualizado)

writer.guardar()
print("\nescribir_contraloria probado - revisa filas 4/5, columnas EB-EG")

from src.core.models import Sentenciado

top3_ejemplo = [
    Sentenciado(numero_proceso="09333202600398", fecha_resolucion="18/08/2026", infraccion="282 INCUMPLIMIENTO DE DECISIONES LEGÍTIMAS DE AUTORIDAD COMPETENTE, INC.1"),
    Sentenciado(numero_proceso="17U05202600018", fecha_resolucion="02/04/2026", infraccion="369 DELICUENCIA ORGANIZADA INC 3"),
]
writer.escribir_sentenciados(fila_excel=4, total_encontrado=2, top3=top3_ejemplo)
writer.guardar()
print("\nescribir_sentenciados probado - revisa fila 4, columnas EM-EY (slot 3 debe tener '-' en las 4 columnas)")

from src.core.models import ProcesoJudicial

procesos_ejemplo = [
    ProcesoJudicial(numero_proceso="17230-2024-00186", materia="FACTURAS O DOCUMENTOS ART. 356 NUM.2", accion_infraccion_delito="FACTURAS O DOCUMENTOS ART. 356 NUM.2", lugar="UNIDAD JUDICIAL CIVIL...", fecha_ingreso="15/03/2024", resumen_ia="Resumen de ejemplo"),
    ProcesoJudicial(numero_proceso="17294-2022-04032G", materia="ARCHIVO...", accion_infraccion_delito="ARCHIVO DE LA INVESTIGACIÓN PREVIA ART. 586", lugar="UNIDAD JUDICIAL PENAL...", fecha_ingreso="10/01/2022", resumen_ia="Otro resumen"),
    ProcesoJudicial(numero_proceso="17371-2022-02501", excluido_por_materia=True),
    ProcesoJudicial(numero_proceso="17371-2014-4451", excluido_por_materia=True),
]
writer.escribir_funcion_judicial(fila_excel=4, procesos=procesos_ejemplo, total_procesos=4, tematica_general="Civil/Mercantil")
writer.guardar()
print("\nescribir_funcion_judicial probado - revisa fila 4, columnas EZ-FP (slot 3 debe tener '-' en las 5 columnas)")

resultados_todo_bien = {
    "sri_ruc": {"razon_social": "..."},
    "antecedentes_penales": True,
    "contraloria": [],
}
writer.escribir_estado_final(fila_excel=4, resultados=resultados_todo_bien)

resultados_con_pendiente = {
    "sri_ruc": {"razon_social": "..."},
    "scvs_companias": {"error": "Timeout", "requiere_revision_manual": True},
}
writer.escribir_estado_final(fila_excel=5, resultados=resultados_con_pendiente)

writer.guardar()
print("\nescribir_estado_final probado - fila 4 debe decir 'Completado', fila 5 'Completado con pendientes'")

resultados_ejemplo = [
    {"apellidos_nombres": "ALVAREZ HENRIQUES AQUILES DAVID", "cargo": "ALCALDE", "entidad": "GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DE GUAYAQUIL", "año": "2025"},
    {"apellidos_nombres": "ALVAREZ HENRIQUES AQUILES DAVID", "cargo": "ALCALDE", "entidad": "GOBIERNO AUTÓNOMO DESCENTRALIZADO MUNICIPAL DE GUAYAQUIL", "año": "2024"},
    {"apellidos_nombres": "ALVAREZ HENRIQUES AQUILES DAVID", "cargo": "ALCALDE DE GUAYAQUIL", "entidad": "M.I. MUNICIPIO DE GUAYAQUIL", "año": "2024"},
    {"apellidos_nombres": "ALVAREZ HENRIQUES AQUILES DAVID", "cargo": "ALCALDE", "entidad": "GOBIERNO AUTÓNOMO DESCENTRALIZADO MUNICIPAL DE GUAYAQUIL", "año": "2023"},
]

from src.scrapers.sitio_contraloria import ScraperContraloria
scraper = ScraperContraloria(context=None, url_base="")
resumen_general = scraper.resumen_general_por_cargo(resultados_ejemplo)
print("Resumen general:", resumen_general)

writer.escribir_contraloria_resumen_general(fila_excel=4, resumen_general=resumen_general)
writer.guardar()

from src.core.models import Denuncia

denuncias_ejemplo = [
    Denuncia(numero_noticia_delito="170101813030869", delito="EXTORSION", estado_rol_cliente="DENUNCIANTE"),
    Denuncia(numero_noticia_delito="170101819060571", delito="DEFRAUDACIÓN TRIBUTARIA", estado_rol_cliente="SOSPECHOSO"),
]

from src.scrapers.sitio_fiscalia import ScraperFiscalia
scraper_fiscalia = ScraperFiscalia(context=None, url_base="")
resumen_fiscalia = scraper_fiscalia.resumen_general_por_denuncia(denuncias_ejemplo)
print("Resumen Fiscalía:", resumen_fiscalia)

writer.escribir_fiscalia_resumen_general(fila_excel=4, resumen_general=resumen_fiscalia)
writer.guardar()
print("\nescribir_fiscalia_resumen_general probado - revisa fila 4, columna FV")