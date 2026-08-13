from dataclasses import dataclass, field
from enum import Enum
from dataclasses import dataclass, field

class TipoPersona(str, Enum):
    NATURAL = "natural"
    JURIDICA = "juridica"


@dataclass
class Cliente:
    identificacion: str
    tipo_persona: TipoPersona
    nombres_completos: str = ""   # formato "Apellidos Nombres", solo Natural
    razon_social: str = ""        # solo Juridica con razón social propia
    fila_excel: int = 0

    @property
    def nombre_para_mostrar(self) -> str:
        if self.tipo_persona == TipoPersona.NATURAL:
            return self.nombres_completos
        return self.razon_social.strip() or self.nombres_completos

class ResultadoConsulta(str, Enum):
    EXITO = "exito"
    TIMEOUT = "timeout"
    ERROR_CAPTCHA = "error_captcha"
    SIN_DATOS = "sin_datos"
    ERROR_DESCONOCIDO = "error_desconocido"

@dataclass
class ProcesoJudicial:
    numero_proceso: str
    demandado: str = ""
    lugar: str = ""
    materia: str = ""
    accion_infraccion_delito: str = ""
    fecha_ingreso: str = ""
    omitido_por_volumen: bool = False
    excluido_por_materia: bool = False
    resumen_ia: str = ""  # se reutiliza para mensajes de omisión, no resumen de IA en este proyecto
    ruta_pdf: str = ""    # sin uso en este proyecto (no se descarga PDF), se deja por compatibilidad

@dataclass
class Denuncia:
    numero_noticia_delito: str
    lugar: str = ""
    fecha: str = ""
    delito: str = ""
    estado_rol_cliente: str = ""
    nombre_sospechoso: str = ""
    unidad_fiscalia: str = ""

