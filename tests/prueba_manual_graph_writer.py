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

writer.guardar()  # solo cierra la sesión, no escribe nada
print("\nSesión cerrada correctamente.")