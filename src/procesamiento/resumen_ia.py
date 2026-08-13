import io
from openai import OpenAI
from pypdf import PdfReader

PROMPT_SISTEMA = (
    "A continuación se presentan uno o dos documentos judiciales ecuatorianos "
    "del MISMO proceso, correspondientes a las dos actuaciones más recientes "
    "(si hay dos, están separados por la marca '--- SIGUIENTE DOCUMENTO ---', "
    "ordenados del más reciente al más antiguo). Trátalos como partes de un "
    "mismo expediente, no como casos distintos. Genera un ÚNICO resumen "
    "ejecutivo general de máximo 350 caracteres, sintetizando la información "
    "de ambos documentos cuando estén presentes. Identifica estrictamente: "
    "1) Objeto o motivo de la demanda, "
    "2) Rol del consultado (si actúa como actor/demandante o demandado), "
    "3) Cuantía o monto económico estimado si lo menciona alguno de los documentos, y "
    "4) Situación procesal actual (basada en la actuación MÁS RECIENTE de las presentadas)."
)


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    lector = PdfReader(io.BytesIO(pdf_bytes))
    texto_completo = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    return texto_completo.strip()


def generar_resumen(texto_pdf: str, api_key: str, modelo: str = "gpt-4o-mini") -> str:
    """
    Genera el resumen ejecutivo usando el prompt exacto del spec.
    Si el texto está vacío (PDF escaneado sin capa de texto, necesitaría OCR
    que no está implementado), levanta error explícito en vez de mandar
    un prompt vacío que generaría una respuesta inventada por la IA.
    """
    if not texto_pdf or not texto_pdf.strip():
        raise ValueError(
            "El texto extraído del PDF está vacío - posible documento escaneado "
            "sin capa de texto. No se envía a la IA."
        )

    cliente = OpenAI(api_key=api_key)

    respuesta = cliente.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": texto_pdf[:15000]},
        ],
        max_tokens=200,
        temperature=0.2,
    )

    return respuesta.choices[0].message.content.strip()