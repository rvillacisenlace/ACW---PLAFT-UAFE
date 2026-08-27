import re
from src.procesamiento.normalizacion import normalizar_texto_busqueda

MATERIAS_RELEVANTES = {
    # Penal
    "lavado de activos", "estafa", "enriquecimiento ilicito", "falsificacion",
    "peculado", "trafico de influencias",
    # Civil / Mercantil
    "insolvencia", "quiebra", "cobro de facturas", "ejecucion de garantias",
    "juicio ejecutivo", "dominio", "nulidad", "contractual", "danos y perjuicios",
    # Laboral
    "laboral",
    # Tributario / Administrativo
    # (pendiente: sin palabras clave definidas aún)
    # Inquilinato / Constitucional
    "inquilinato", "constitucional",
    # NOTA: "accion de proteccion" se removió de aquí a propósito -
    # confirmado en reunión que la lista de exclusión oficial (más abajo)
    # tiene prioridad y la excluye siempre. Dejarla aquí sería código
    # muerto, ya que la exclusión se revisa antes que la relevancia.
}

# Lista oficial de materias/tipos de proceso a EXCLUIR, provista por el
# equipo legal (reunión del 29/07/2026). Se mantiene como texto plano
# para poder actualizarla fácilmente pegando una lista nueva completa,
# sin tener que editar un set() de Python a mano.
_LISTA_EXCLUSION_RAW = """
Violencia intrafamiliar y de género

ART. 156 Violencia física contra la mujer o miembros del núcleo familiar
ART. 157 Violencia psicológica contra la mujer o miembros del núcleo familiar
ART. 158 Violencia sexual contra la mujer o miembros del núcleo familiar
ART. 159 Contravenciones de violencia contra la mujer o miembros del núcleo familiar
ART. 164 Inseminación no consentida
ART. 166 Acoso sexual
ART. 167 Estupro
ART. 172 Utilización de personas para exhibición pública con fines de naturaleza sexual

Personas protegidas / DIH (conflicto armado)

ART. 085 Ejecución extrajudicial
ART. 088 Agresión
ART. 115 Homicidio de persona protegida
ART. 116 Atentado a la integridad sexual y reproductiva de persona protegida
ART. 117 Lesión a la integridad física de persona protegida
ART. 119 Tortura y tratos crueles, inhumanos o degradantes en persona protegida
ART. 123 Ataque a bienes protegidos
ART. 125 Privación de libertad de persona protegida
ART. 131 Abolición y suspensión de derechos de persona protegida
ART. 134 Omisión de medidas de socorro y asistencia humanitaria
ART. 135 Omisión de medidas de protección
ART. 137 Prolongación de hostilidades

Salud / vida (culposos, aborto, mala práctica)

ART. 145 Homicidio culposo
ART. 146 Homicidio culposo por mala práctica profesional
ART. 147 Aborto con muerte
ART. 148 Aborto no consentido
ART. 149 Aborto consentido
ART. 152 Lesiones
ART. 153 Abandono de persona
ART. 215 Daño permanente a la salud
ART. 218 Desatención del servicio de salud
ART. 276 Omisión de denuncia por parte de un profesional de la salud
ART. 328.1 Falsedad de contenido en recetas, exámenes o certificados médicos
ART. 329 Falsificación, forjamiento o alteración de recetas
ART. 330 Ejercicio ilegal de la profesión

Discriminación, honor e intimidad

ART. 154.3 Acoso escolar y académico
ART. 176 Discriminación
ART. 177 Actos de odio
ART. 178 Violación a la intimidad
ART. 179 Revelación de secreto
ART. 180 Difusión de información de circulación restringida
ART. 181 Violación de propiedad privada
ART. 182 Calumnia
ART. 183 Restricción a la libertad de expresión
ART. 184 Restricción a la libertad de culto
ART. 233 Delitos contra la información pública reservada legalmente
ART. 234 Acceso no consentido a un sistema informático, telemático o de telecomunicaciones

Patrimonio menor / hurto

ART. 209 Contravención de hurto
ART. 210 Contravención de abigeato
ART. 211 Supresión, alteración o suposición de la identidad y estado civil
ART. 235 Engaño al comprador respecto a la identidad o calidad de las cosas o servicios vendidos

Seguridad social

ART. 242 Retención ilegal de aportación a la seguridad social
ART. 243 Falta de afiliación al IESS por parte de una persona jurídica
ART. 244 Falta de afiliación al IESS

Ambiental y fauna

ART. 245 Invasión de áreas de importancia ecológica
ART. 246 Incendios forestales y de vegetación
ART. 247 Delitos contra la flora y fauna silvestres
ART. 248 Delitos contra los recursos del patrimonio genético nacional
ART. 249 Lesiones a animales que formen parte del ámbito de la fauna urbana
ART. 250 Abuso sexual a animales que forman parte del ámbito de la fauna urbana
ART. 250.1 Muerte a animal que forma parte del ámbito de la fauna urbana
ART. 250.2 Peleas o combates entre perros u otros animales de fauna urbana
ART. 250.3 Abandono de animales de compañía
ART. 250.4 Maltrato a animales que forman parte del ámbito de la fauna urbana
ART. 251 Delitos contra el agua
ART. 252 Delitos contra suelo
ART. 253 Contaminación del aire
ART. 254 Gestión prohibida o no autorizada de productos, residuos, desechos o sustancias peligrosas
ART. 255 Falsedad u ocultamiento de información ambiental

Administración de justicia

ART. 270 Perjurio y falso testimonio
ART. 271 Acusación o denuncia maliciosa
ART. 277 Omisión de denuncia
ART. 282 Incumplimiento de decisiones legítimas de autoridad competente
ART. 283 Ataque o resistencia
ART. 284 Ruptura de sellos
ART. 292 Alteración de evidencias y elementos de prueba
ART. 311 Ocultamiento de información
ART. 312 Falsedad de información
ART. 326 Descuento indebido de valores

Función pública / fuerza pública

ART. 225 Acciones de mala fe para involucrar en delitos
ART. 288 Uso de fuerza pública contra órdenes de autoridad
ART. 291 Elusión de responsabilidades de servidores de FF.AA. o Policía Nacional
ART. 293 Extralimitación en la ejecución de un acto de servicio
ART. 294 Abuso de facultades
ART. 295 Negativa a prestar auxilio solicitado por autoridad civil
ART. 296 Usurpación de uniformes e insignias
ART. 342 Sedición
ART. 343 Insubordinación
ART. 344 Abstención de la ejecución de operaciones en conmoción interna
ART. 351 Infiltración en zonas de seguridad
ART. 357 Deserción
ART. 358 Omisión de aviso de deserción
ART. 363 Instigación

Electoral

ART. 331 Obstaculización de proceso electoral
ART. 332 Sustracción de papeletas electorales
ART. 333 Falso sufragio
ART. 334 Fraude electoral

Orden público / servicios

ART. 346 Paralización de un servicio público
ART. 347 Destrucción de registros
ART. 348 Incitación a discordia entre ciudadanos
ART. 349 Grupos subversivos
ART. 364 Incendio

Tránsito

ART. 376 Muerte causada por conductor en estado de embriaguez o bajo los efectos de sustancias estupefacientes, psicotropicas o preparados que las contengan
ART. 377 Muerte culposa
ART. 378 Muerte provocada por negligencia de contratista o ejecutor de obra
ART. 379 Lesiones causadas por accidente de transito
ART. 380 Daños materiales
ART. 381 Exceso de pasajeros en transporte público
ART. 382 Daños mecánicos previsibles en transporte público
ART. 383 Conducción de vehículo con llantas en mal estado
ART. 384 Conducción de vehículo bajo efecto de sustancias estupefacientes, psicotropicas o preparados que las contengan
ART. 385 Conducción de vehículo en estado de embriaguez
ART. 386 Contravenciones de transito de primera clase
ART. 387 Contravenciones de transito de segunda clase
ART. 388 Contravenciones de transito de tercera clase
ART. 389 Contravenciones de transito de cuarta clase
ART. 390 Contravenciones de transito de quinta clase
ART. 391 Contravenciones de transito de sexta clase
ART. 392 Contravenciones de transito de septima clase

Contravenciones generales

ART. 393 Contravenciones de primera clase
ART. 394 Contravenciones de segunda clase
ART. 395 Contravenciones de tercera clase
ART. 396 Contravenciones de cuarta clase
ART. 397 Contravenciones en escenarios deportivos y de concurrencia masiva

Sin categoría clara / verificar

ART. 072 Extinción de la pena
"""

_ENCABEZADOS_SECCION = {
    "VIOLENCIA INTRAFAMILIAR Y DE GÉNERO",
    "PERSONAS PROTEGIDAS / DIH (CONFLICTO ARMADO)",
    "SALUD / VIDA (CULPOSOS, ABORTO, MALA PRÁCTICA)",
    "DISCRIMINACIÓN, HONOR E INTIMIDAD",
    "PATRIMONIO MENOR / HURTO",
    "SEGURIDAD SOCIAL",
    "AMBIENTAL Y FAUNA",
    "ADMINISTRACIÓN DE JUSTICIA",
    "FUNCIÓN PÚBLICA / FUERZA PÚBLICA",
    "ELECTORAL",
    "ORDEN PÚBLICO / SERVICIOS",
    "TRÁNSITO",
    "CONTRAVENCIONES GENERALES",
    "SIN CATEGORÍA CLARA / VERIFICAR",
}
_PATRON_PREFIJO_ARTICULO = re.compile(r'^ART\.\s*\d+(?:\.\d+)?\s*(?:[A-Z]\s+)?', re.IGNORECASE)


def _construir_materias_excluidas() -> set:
    """
    Procesa la lista oficial cruda: quita encabezados de sección, quita
    el prefijo 'ART. 123 ' de las entradas del COIP (el texto real
    capturado del portal normalmente no incluye la palabra "ART."), y
    normaliza cada frase con el mismo normalizador usado en todo el
    sistema, para que la comparación sea consistente.
    """
    excluidas = set()
    for linea in _LISTA_EXCLUSION_RAW.strip().split("\n"):
        linea = linea.strip()
        if not linea or linea.upper() in _ENCABEZADOS_SECCION:
            continue
        sin_prefijo = _PATRON_PREFIJO_ARTICULO.sub("", linea).strip()
        normalizada = normalizar_texto_busqueda(sin_prefijo)
        if normalizada:
            excluidas.add(normalizada)
    return excluidas


MATERIAS_EXCLUIDAS = _construir_materias_excluidas()


def es_materia_relevante(materia_o_accion: str) -> bool:
    """
    Recibe el texto de 'materia' o, si no está disponible, el texto de
    'Acción/Infracción/Delito'.

    NOTA: esta función es una primera pasada por palabras/frases clave.
    No es infalible - un abogado debe seguir revisando los casos límite.

    DECISIÓN CONFIRMADA (reunión 29/07/2026): ante conflicto entre la
    lista oficial de exclusión y la lista de relevantes, la exclusión
    oficial SIEMPRE gana (se revisa primero en el código). Esto incluye
    casos que antes se consideraban relevantes por defecto, como
    "DESPIDO INTEMPESTIVO" / "INDEMNIZACIÓN POR DESPIDO INTEMPESTIVO"
    (ahora excluidos) y "ACCIÓN DE PROTECCIÓN" (ahora excluida, pese a
    estar también en la lista de relevantes de Constitucional).
    """
    texto_normalizado = normalizar_texto_busqueda(materia_o_accion).lower()

    if any(excluida.lower() in texto_normalizado for excluida in MATERIAS_EXCLUIDAS):
        return False

    if any(relevante in texto_normalizado for relevante in MATERIAS_RELEVANTES):
        return True

    return True  # decisión conservadora: mejor mostrar de más que ocultar algo importante

# Mapeo de palabra clave -> categoría general, para la columna "Temática
# Juicios" de la matriz. Usa las mismas palabras que ya están en
# MATERIAS_RELEVANTES, agrupadas por categoría explícita.
_CATEGORIA_POR_PALABRA = {
    # Penal
    "lavado de activos": "Penal", "estafa": "Penal", "enriquecimiento ilicito": "Penal",
    "falsificacion": "Penal", "peculado": "Penal", "trafico de influencias": "Penal",
    "archivo de la investigacion previa": "Penal", "investigacion previa": "Penal",
    # Civil / Mercantil
    "insolvencia": "Civil/Mercantil", "quiebra": "Civil/Mercantil",
    "cobro de facturas": "Civil/Mercantil", "ejecucion de garantias": "Civil/Mercantil",
    "juicio ejecutivo": "Civil/Mercantil", "dominio": "Civil/Mercantil",
    "nulidad": "Civil/Mercantil", "contractual": "Civil/Mercantil",
    "danos y perjuicios": "Civil/Mercantil", "facturas": "Civil/Mercantil",
    # Laboral
    "laboral": "Laboral",
    # Inquilinato / Constitucional
    "inquilinato": "Inquilinato/Constitucional", "constitucional": "Inquilinato/Constitucional",
}


def clasificar_categoria(materia_o_accion: str) -> str:
    """
    Determina la categoría general (Civil/Mercantil, Penal, Laboral,
    Inquilinato/Constitucional) de un proceso, para la columna "Temática
    Juicios" de la matriz. Reutiliza las mismas palabras clave que
    es_materia_relevante(), sin duplicar la lista.
    """
    texto_normalizado = normalizar_texto_busqueda(materia_o_accion).lower()

    for palabra, categoria in _CATEGORIA_POR_PALABRA.items():
        if palabra in texto_normalizado:
            return categoria

    return ""  # no coincide con ninguna categoría conocida