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

@dataclass
class Sentenciado:
    numero_proceso: str
    provincia: str = ""
    dependencia_jurisdiccional: str = ""
    fecha_resolucion: str = ""
    materia: str = ""
    tipo_accion: str = ""
    infraccion: str = ""
    ruta_pdf: str = ""

@dataclass
class AntecedentePenal:
    nombre: str = ""
    tipo_documento: str = ""
    numero_documento: str = ""
    posee_antecedentes: str = ""
    ruta_pdf: str = ""

@dataclass
class Salud:
    ruta_pdf: str = ""
    situacion_laboral: str = ""  # "Relación de Dependencia (IESS)", por ejemplo
    tipo_afiliacion: str = ""    # valor de "Tipo de seguro" de la fila con cobertura

@dataclass
class IESS:
    ruta_pdf: str = ""
    iess: str = ""              # texto tal cual: "SI registra obligaciones patronales en mora" / "NO registra..."
    deuda_obligaciones: str = ""  # solo el valor, ej. "12,683.75"

@dataclass
class DeudaSRI:
    tiene_deuda_firme: bool = False
    valor_deuda_firme: str = "$0.00"
    mensaje: str = ""