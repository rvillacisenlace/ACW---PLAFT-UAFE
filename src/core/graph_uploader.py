"""
src/core/graph_uploader.py

Sube archivos (PDFs, evidencia) a OneDrive vía Graph API, replicando la
misma estructura de carpetas que ya existe en local
(DebidaDiligencia/Año/Mes/Identificacion/archivo). El guardado local
sigue existiendo como respaldo/staging - esto es una copia adicional,
no un reemplazo.
"""
import os
import requests


class GraphUploader:
    def __init__(self, cuenta_onedrive: str, writer, carpeta_base: str = "COMPARTIDO/LEGAL"):
        """
        writer: instancia de GraphAPIWriter, reutilizada para obtener
        siempre un token fresco (writer._refrescar_token()) antes de subir
        cada archivo - evita fallos por expiración en corridas largas.
        """
        self.cuenta_onedrive = cuenta_onedrive
        self.writer = writer
        self.carpeta_base = carpeta_base

    def subir_archivo(self, ruta_local: str, identificacion_cliente: str, año: str, mes: str) -> str:
        """
        Sube un archivo local a OneDrive, replicando la estructura
        DebidaDiligencia/Año/Mes/Identificacion/nombre_archivo.
        Devuelve la URL del archivo subido, o lanza excepción si falla.
        """
        nombre_archivo = os.path.basename(ruta_local)
        ruta_onedrive = (
            f"{self.carpeta_base}/DebidaDiligencia/{año}/{mes}/"
            f"{identificacion_cliente}/{nombre_archivo}"
        )

        with open(ruta_local, "rb") as f:
            contenido = f.read()

        # PUT simple: válido para archivos hasta 4MB (suficiente para PDFs
        # y capturas de pantalla individuales de este proyecto). Archivos
        # más grandes necesitarían "upload session" - no implementado aquí,
        # ya que no se han visto casos que lo requieran.
        url = (
            f"https://graph.microsoft.com/v1.0/users/{self.cuenta_onedrive}"
            f"/drive/root:/{ruta_onedrive}:/content"
        )

        self.writer._refrescar_token()
        resp = requests.put(url, headers=self.writer.headers, data=contenido)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Falló la subida de {nombre_archivo} a OneDrive: "
                f"{resp.status_code} - {resp.text[:300]}"
            )

        return resp.json().get("webUrl", "")