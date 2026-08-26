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
    nombres_completos: str = ""
    razon_social: str = ""
    fila_excel: int = 0
    # Usados SOLO cuando este objeto Cliente representa al representante
    # legal de una empresa (ver main.py, cliente_para_persona). Permiten
    # que la evidencia quede anidada dentro de la carpeta de la empresa
    # en vez de crear una carpeta separada con la cedula del RL.
    identificacion_evidencia: str = ""  # si esta vacio, se usa identificacion normal
    subcarpeta_evidencia: str = ""      # ej. "representante_legal"

    @property
    def nombre_para_mostrar(self) -> str:
        if self.tipo_persona == TipoPersona.NATURAL:
            return self.nombres_completos
        return self.razon_social.strip() or self.nombres_completos

    @property
    def es_juridica_con_ruc_persona_natural(self) -> bool:
        """
        Caso especial: cliente marcado como Jurídica, pero sin razón
        social propia y con nombres_completos lleno - indica que en
        realidad es una persona natural con RUC propio (negocio
        unipersonal), no una empresa real. Se le aplica la misma lógica
        de búsqueda robusta que a un cliente Natural.
        """
        return (
            self.tipo_persona == TipoPersona.JURIDICA
            and not self.razon_social.strip()
            and bool(self.nombres_completos.strip())
        )

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

@dataclass
class EstadoTributarioSRI:
    resultado: str = ""              # "AL DIA EN SUS OBLIGACIONES" u otro estado
    obligaciones_pendientes: str = ""  # ej. "2011 DECLARACION DE IVA MAYO 2026 / ..."

@dataclass
class CompaniaSCVS:
    ruc: str = ""
    expediente: str = ""
    representante_legal_scvs_referencia: str = ""  # texto completo, solo referencia - NO sobreescribe el del SRI
    capital_social: str = ""
    situacion_legal: str = ""
    cumplimiento_obligaciones: str = ""
    fecha_consulta: str = ""
    registrado: bool = True
    mensaje: str = ""
    ruta_pdf: str = ""

@dataclass
class DeudaMunicipal:
    tiene_deuda: bool = False
    valor_total: str = "$0.00"
    registrado: bool = True
    mensaje: str = ""