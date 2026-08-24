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
#writer.escribir_antecedentes_penales(fila_excel=clientes[0].fila_excel, posee_antecedentes=False)
#writer.guardar()

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