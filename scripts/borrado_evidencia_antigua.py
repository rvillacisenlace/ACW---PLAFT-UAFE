"""
Borrado manual de evidencia antigua de Debida Diligencia.

Solicitado por el equipo de Cumplimiento (reunion 2026-09-03): conservar
SOLO la evidencia de la PRIMERA consulta hecha a cada cliente, y borrar
toda evidencia de consultas posteriores. Ejemplo: si un cliente fue
consultado el 10-agosto y de nuevo 5 veces mas hasta el 2-septiembre,
se conserva unicamente lo del 10-agosto y se borran las otras 5.

Este script es MANUAL - no se ejecuta automaticamente dentro de
main.py. El usuario lo corre cuando decide hacer limpieza.

Por seguridad (accion irreversible), el script SIEMPRE corre primero en
modo vista previa (no borra nada) y muestra exactamente que se
eliminaria. Solo borra de verdad si se pasa --confirmar Y se escribe
"BORRAR" cuando se pide confirmacion.

Uso:
    python -m scripts.borrado_evidencia_antigua                 # vista previa, no borra nada
    python -m scripts.borrado_evidencia_antigua --confirmar     # pide confirmacion y borra

Criterio de "fecha de consulta" de un archivo: se usa la fecha de
MODIFICACION del archivo en disco (mtime), no el nombre del archivo -
los PDFs no tienen fecha en el nombre (solo el numero de proceso), asi
que mtime es el unico criterio que funciona igual para PDFs y capturas.

Un mismo cliente (misma identificacion) puede tener evidencia repartida
en varias carpetas Año/Mes distintas si se le consulto en meses
diferentes - este script agrupa por identificacion SIN IMPORTAR en que
Año/Mes este la carpeta, para encontrar la fecha real mas antigua de
consulta de ese cliente en TODO el historial, no solo dentro de una
carpeta de mes.

La subcarpeta de representante_legal_XXX se trata como parte del mismo
cliente (mismo identificador raiz), no como un cliente aparte.
"""
import os
import sys
from datetime import datetime, date
from collections import defaultdict

BASE_DIR = "./data/staging/DebidaDiligencia"


def _identificacion_desde_ruta(ruta_relativa: str) -> str | None:
    """
    Dada una ruta relativa a BASE_DIR (ej. "2026/08/1001322518/sri/archivo.pdf"
    o "2026/09/1890010705001/representante_legal_1801099787/salud/x.pdf"),
    extrae la identificacion del cliente (siempre el 3er segmento: Año/Mes/Identificacion/...).
    """
    partes = ruta_relativa.replace(os.sep, "/").split("/")
    if len(partes) < 3:
        return None
    return partes[2]


def _recolectar_archivos_por_cliente() -> dict[str, list[tuple[str, date]]]:
    """
    Devuelve {identificacion_cliente: [(ruta_absoluta, fecha_mtime), ...]}
    recorriendo TODA la estructura Año/Mes/Identificacion, sin importar
    en que Año/Mes este cada carpeta.
    """
    archivos_por_cliente: dict[str, list[tuple[str, date]]] = defaultdict(list)

    if not os.path.isdir(BASE_DIR):
        return archivos_por_cliente

    for raiz, _, archivos in os.walk(BASE_DIR):
        ruta_relativa_raiz = os.path.relpath(raiz, BASE_DIR)
        for nombre_archivo in archivos:
            ruta_absoluta = os.path.join(raiz, nombre_archivo)
            ruta_relativa_completa = os.path.join(ruta_relativa_raiz, nombre_archivo)
            identificacion = _identificacion_desde_ruta(ruta_relativa_completa)
            if identificacion is None:
                continue
            fecha_mtime = date.fromtimestamp(os.path.getmtime(ruta_absoluta))
            archivos_por_cliente[identificacion].append((ruta_absoluta, fecha_mtime))

    return archivos_por_cliente


def calcular_plan_de_borrado() -> dict[str, dict]:
    """
    Para cada cliente, determina la fecha mas antigua y separa sus
    archivos en "conservar" (esa fecha) vs "borrar" (cualquier otra).
    """
    archivos_por_cliente = _recolectar_archivos_por_cliente()
    plan = {}

    for identificacion, archivos in archivos_por_cliente.items():
        fecha_mas_antigua = min(fecha for _, fecha in archivos)
        conservar = [ruta for ruta, fecha in archivos if fecha == fecha_mas_antigua]
        borrar = [ruta for ruta, fecha in archivos if fecha != fecha_mas_antigua]
        plan[identificacion] = {
            "fecha_primera_consulta": fecha_mas_antigua,
            "conservar": conservar,
            "borrar": borrar,
        }

    return plan


def mostrar_vista_previa(plan: dict[str, dict]) -> int:
    """Imprime el plan de borrado y devuelve el total de archivos a borrar."""
    total_a_borrar = 0
    total_tamano_bytes = 0

    print(f"\n{'='*70}")
    print("VISTA PREVIA - BORRADO DE EVIDENCIA ANTIGUA")
    print(f"{'='*70}\n")

    if not plan:
        print("No se encontró evidencia en", BASE_DIR)
        return 0

    for identificacion, info in sorted(plan.items()):
        if not info["borrar"]:
            continue  # cliente con una sola fecha de consulta - nada que borrar
        print(f"Cliente {identificacion}:")
        print(f"  Primera consulta (SE CONSERVA): {info['fecha_primera_consulta']} - {len(info['conservar'])} archivo(s)")
        print(f"  Consultas posteriores (SE BORRARÁN): {len(info['borrar'])} archivo(s)")
        for ruta in info["borrar"]:
            tamano = os.path.getsize(ruta)
            total_tamano_bytes += tamano
            total_a_borrar += 1
        print()

    print(f"{'='*70}")
    print(f"TOTAL: {total_a_borrar} archivo(s) se eliminarían ({total_tamano_bytes / 1024 / 1024:.1f} MB)")
    print(f"{'='*70}\n")

    return total_a_borrar


def ejecutar_borrado(plan: dict[str, dict]) -> None:
    eliminados = 0
    fallidos = 0
    for identificacion, info in plan.items():
        for ruta in info["borrar"]:
            try:
                os.remove(ruta)
                eliminados += 1
            except Exception as e:
                print(f"  [ERROR] No se pudo borrar {ruta}: {type(e).__name__}: {e}")
                fallidos += 1

    print(f"\nBorrado completado: {eliminados} archivo(s) eliminados, {fallidos} fallido(s).")


def main():
    plan = calcular_plan_de_borrado()
    total_a_borrar = mostrar_vista_previa(plan)

    if total_a_borrar == 0:
        print("Nada que borrar - no se requiere ninguna acción.")
        return

    if "--confirmar" not in sys.argv:
        print("Esto fue solo una VISTA PREVIA - no se borró nada.")
        print("Para borrar de verdad, corre: python -m scripts.borrado_evidencia_antigua --confirmar")
        return

    print("¡ATENCIÓN! Esta acción es IRREVERSIBLE.")
    respuesta = input(f"Escribe BORRAR (en mayúsculas) para eliminar los {total_a_borrar} archivos listados arriba: ")
    if respuesta.strip() != "BORRAR":
        print("Confirmación no coincide - operación cancelada, no se borró nada.")
        return

    ejecutar_borrado(plan)


if __name__ == "__main__":
    main()