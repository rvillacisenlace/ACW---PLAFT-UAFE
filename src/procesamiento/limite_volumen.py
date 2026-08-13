from datetime import datetime
from src.core.models import ProcesoJudicial
from src.procesamiento.clasificador import es_materia_relevante

UMBRAL_VOLUMEN = 3

def aplicar_limite_volumen(procesos: list[ProcesoJudicial]) -> list[ProcesoJudicial]:
    """
    Ordena EXPLÍCITAMENTE por fecha_ingreso (más reciente primero) antes de
    aplicar el límite.
    """
    def parsear_fecha(proceso: ProcesoJudicial) -> datetime:
        try:
            return datetime.strptime(proceso.fecha_ingreso, "%d/%m/%Y")
        except ValueError:
            print(f"ADVERTENCIA: fecha_ingreso inválida en proceso {proceso.numero_proceso}: '{proceso.fecha_ingreso}' - se trata como la más antigua posible.")
            return datetime.min

    ordenados = sorted(procesos, key=parsear_fecha, reverse=True)

    for proceso in ordenados[UMBRAL_VOLUMEN:]:
        proceso.omitido_por_volumen = True
        proceso.resumen_ia = "Proceso omitido por límite de volumen. Revisar manualmente"

    return ordenados

def separar_por_materia(procesos: list[ProcesoJudicial]) -> tuple[list[ProcesoJudicial], list[ProcesoJudicial]]:
    """
    Separa los procesos en (relevantes, excluidos por materia) usando el
    texto de Acción/Infracción de la tabla principal - disponible sin
    necesidad de abrir el detalle. El límite de volumen debe aplicarse
    SOLO sobre los relevantes, para que un proceso excluido no ocupe un
    cupo del top 10 (spec: "Masivas... filtrar únicamente por materias...").
    """
    relevantes, excluidos = [], []
    for proceso in procesos:
        if es_materia_relevante(proceso.accion_infraccion_delito):
            relevantes.append(proceso)
        else:
            proceso.excluido_por_materia = True
            proceso.resumen_ia = (
                "Materia excluida por política (Tránsito/Familia/Contravención "
                "menor). No se descargó PDF ni se generó resumen."
            )
            excluidos.append(proceso)
    return relevantes, excluidos