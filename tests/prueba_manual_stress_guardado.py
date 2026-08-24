from src.core.excel_writer import LocalExcelWriter

writer = LocalExcelWriter("templates/Matriz Revisión Clientes.xlsx")

for i in range(5):
    print(f"--- Guardado {i + 1}/5 ---")
    writer.escribir_antecedentes_penales(fila_excel=4, posee_antecedentes=(i % 2 == 0))
    writer.guardar()
    print(f"Guardado {i + 1}/5: OK")

print("\n5/5 guardados completados sin errores.")