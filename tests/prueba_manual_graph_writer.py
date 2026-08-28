from config.settings import cargar_infra_config
from src.core.excel_writer import GraphAPIWriter

infra = cargar_infra_config()

writer = GraphAPIWriter(
    cuenta_onedrive=infra.cuenta_onedrive,
    drive_id=infra.graph_drive_id,
    item_id=infra.graph_excel_item_id,
    tenant_id=infra.azure_tenant_id,
    client_id=infra.azure_client_id,
    client_secret=infra.azure_client_secret,
    nombre_hoja="Revision",
)
print("Conexión establecida y sesión de Graph API creada correctamente.\n")

clientes = writer.leer_clientes_pendientes()
print(f"Total clientes pendientes: {len(clientes)}\n")
for c in clientes[:10]:
    print(f"Fila {c.fila_excel}: {c.identificacion} | {c.tipo_persona} | {c.nombres_completos or c.razon_social}")

parametros = writer.leer_parametrizacion()
print(f"\nTotal parámetros: {len(parametros)}")

import time

inicio = time.monotonic()
writer.escribir_antecedentes_penales(fila_excel=4, posee_antecedentes=False)
duracion = time.monotonic() - inicio
print(f"\nescribir_antecedentes_penales via Graph API: {duracion:.2f} segundos")

writer.escribir_sri_ruc(fila_excel=4, datos={
    "razon_social": "TORRES GORDILLO DIEGO PATRICIO",
    "estado_contribuyente": "ACTIVO",
    "actividad_economica": "ACTIVIDADES DE CONSULTORIA",
})
print("\nescribir_sri_ruc via Graph API: OK - revisa fila 4, columna N (SRI Razón Social)")

writer.escribir_contraloria(fila_excel=4, resumen={
    "posee_declaraciones": "SI",
    "vigencia": "Desactualizado",
    "cargo": "-",
    "tiempo": "-",
    "ultimo_anio_en_cargo": "-",
})
print("escribir_contraloria via Graph API: OK - revisa fila 4, columnas EB-EG")

writer.escribir_sri_deudas(fila_excel=5, tiene_deuda_firme=True, valor_deuda_firme="$150.00")
writer.escribir_sri_estado_tributario(fila_excel=4, resultado="AL DIA EN SUS OBLIGACIONES")
print("escribir_sri_deudas + escribir_sri_estado_tributario: OK - revisa fila 4/5, columnas AD/AE")

from src.core.models import DeudaMunicipal
resultados_municipios = {
    "Quito": DeudaMunicipal(tiene_deuda=True, valor_total="$15.00", registrado=True),
    "Cuenca": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=True),
    "Ambato": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Esmeraldas": DeudaMunicipal(tiene_deuda=False, valor_total="$0.00", registrado=False),
    "Manta": DeudaMunicipal(tiene_deuda=True, valor_total="$37.63", registrado=True),
}
writer.escribir_municipios(fila_excel=4, resultados=resultados_municipios)
print("escribir_municipios: OK - revisa fila 4, columnas AF/AG")

writer.escribir_sercop_proveedor(fila_excel=4, estado="PROVEEDOR DEL ESTADO")
writer.escribir_sercop_certificados(fila_excel=4, datos={
    "contratos_pendientes": {"resultado": "NO"},
    "incumplimientos": {"resultado": "NO"},
})
print("escribir_sercop_proveedor + certificados: OK - revisa fila 4, columnas AH/AI/AJ")

writer.escribir_salud(fila_excel=4, situacion_laboral="Relación de Dependencia (IESS)", tipo_afiliacion="Voluntario")
writer.escribir_iess(fila_excel=4, iess="NO registra obligaciones patronales en mora", deuda_obligaciones="")
print("escribir_salud + escribir_iess: OK - revisa fila 4, columnas AL/AM/AN/AO")

writer.escribir_scvs_companias(fila_excel=4, registrado=True, cumplimiento_obligaciones="SI HA CUMPLIDO")
print("escribir_scvs_companias: OK - revisa fila 4, columna AR")

from src.core.models import Sentenciado
top3_ejemplo = [
    Sentenciado(numero_proceso="09333202600398", fecha_resolucion="18/08/2026", infraccion="282 INCUMPLIMIENTO DE DECISIONES LEGÍTIMAS DE AUTORIDAD COMPETENTE, INC.1"),
    Sentenciado(numero_proceso="17U05202600018", fecha_resolucion="02/04/2026", infraccion="369 DELICUENCIA ORGANIZADA INC 3"),
]
writer.escribir_sentenciados(fila_excel=4, total_encontrado=2, top3=top3_ejemplo)
print("escribir_sentenciados: OK - revisa fila 4, columnas EM-EY (slot 3 en '-')")

from src.core.models import ProcesoJudicial
procesos_ejemplo = [
    ProcesoJudicial(numero_proceso="17230-2024-00186", accion_infraccion_delito="FACTURAS O DOCUMENTOS ART. 356 NUM.2", fecha_ingreso="15/03/2024", resumen_ia="Resumen de ejemplo"),
    ProcesoJudicial(numero_proceso="17294-2022-04032G", accion_infraccion_delito="ARCHIVO DE LA INVESTIGACIÓN PREVIA ART. 586", fecha_ingreso="10/01/2022", resumen_ia="Otro resumen"),
]
writer.escribir_funcion_judicial(fila_excel=4, procesos=procesos_ejemplo, total_procesos=2, tematica_general="Civil/Mercantil")
print("escribir_funcion_judicial: OK - revisa fila 4, columnas EZ-FP (slot 3 en '-')")

writer.escribir_contraloria_resumen_general(fila_excel=4, resumen_general="ALCALDE - GAD GUAYAQUIL (2025,2024,2023)")
writer.escribir_fiscalia_resumen_general(fila_excel=4, resumen_general="170101813030869 - EXTORSION (DENUNCIANTE)")
print("escribir_contraloria_resumen_general + fiscalia: OK - revisa fila 4, columnas FU/FV")

writer.escribir_estado_final(fila_excel=4, resultados={"sri_ruc": {"ok": True}})
writer.escribir_estado_final(fila_excel=5, resultados={"scvs_companias": {"error": "Timeout", "requiere_revision_manual": True}})
print("escribir_estado_final: OK - fila 4 debe decir 'Completado', fila 5 'Completado con pendientes'")

writer.guardar()  # solo cierra la sesión, no escribe nada
print("\nSesión cerrada correctamente.")