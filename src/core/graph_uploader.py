"""
Sube archivos (PDFs, evidencia) a OneDrive vía Graph API, replicando la
misma estructura de carpetas que ya existe en local
(DebidaDiligencia/Año/Mes/Identificacion/.../archivo). El guardado
local sigue existiendo como respaldo/staging - esto es una copia
adicional, no un reemplazo.
"""
import os
import requests
from datetime import datetime

class GraphUploader:
    def __init__(self, cuenta_onedrive: str, writer, carpeta_base: str = "COMPARTIDO/CUMPLIMIENTO"):
        """
        writer: instancia de GraphAPIWriter, reutilizada para obtener
        siempre un token fresco (writer._refrescar_token()) antes de subir
        cada archivo - evita fallos por expiración en corridas largas.
        """
        self.cuenta_onedrive = cuenta_onedrive
        self.writer = writer
        self.carpeta_base = carpeta_base

    def _subir_un_archivo(self, ruta_local: str, ruta_onedrive: str) -> str:
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
                f"Falló la subida de {os.path.basename(ruta_local)} a OneDrive: "
                f"{resp.status_code} - {resp.text[:300]}"
            )

        return resp.json().get("webUrl", "")

    def subir_carpeta_cliente(self, carpeta_local_cliente: str, identificacion_cliente: str, año: str, mes: str, modificados_desde=None) -> list[str]:
        """
        Sube archivos dentro de la carpeta local de evidencia de un
        cliente, preservando la estructura completa de subcarpetas tal
        cual está en disco.

        modificados_desde: datetime opcional - si se da, SOLO se suben
        archivos cuya fecha de modificación sea posterior a ese momento
        (evita re-subir todo el historial de un cliente en un reintento
        parcial donde solo se re-ejecutó 1 de los 18 sitios - confirmado
        con evidencia real 2026-09-07 que sin esto, se re-sube TODO cada
        vez, no solo lo nuevo). Si es None, sube todo (comportamiento
        original, para una corrida completa nueva).

        Devuelve la lista de nombres de archivo subidos exitosamente.
        Un archivo individual que falle se reporta por consola pero no
        detiene la subida del resto.
        """
        if not os.path.isdir(carpeta_local_cliente):
            return []

        archivos_a_subir = []
        for raiz, _, archivos in os.walk(carpeta_local_cliente):
            for nombre_archivo in archivos:
                ruta_local = os.path.join(raiz, nombre_archivo)
                if modificados_desde is not None:
                    mtime = datetime.fromtimestamp(os.path.getmtime(ruta_local))
                    if mtime < modificados_desde:
                        continue
                ruta_relativa = os.path.relpath(ruta_local, carpeta_local_cliente).replace(os.sep, "/")
                archivos_a_subir.append((ruta_local, ruta_relativa))

        total = len(archivos_a_subir)
        if total == 0:
            return []

        subidos = []
        for i, (ruta_local, ruta_relativa) in enumerate(archivos_a_subir, start=1):
            ruta_onedrive = "/".join([
                self.carpeta_base, "DebidaDiligencia", año, mes, identificacion_cliente, ruta_relativa,
            ])
            try:
                self._subir_un_archivo(ruta_local, ruta_onedrive)
                subidos.append(os.path.basename(ruta_local))
                print(f"    [OneDrive] ({i}/{total}) Subido: {ruta_relativa}")
            except Exception as e:
                print(f"    [OneDrive] ({i}/{total}) Falló: {ruta_relativa} - {type(e).__name__}: {e}")

        return subidos

    def obtener_link_carpeta_cliente(self, identificacion_cliente: str, año: str, mes: str) -> str:
        """
        Devuelve el webUrl real (clicable, abre en el navegador) de la
        carpeta raíz de evidencia de este cliente en OneDrive. Solo
        funciona DESPUÉS de que al menos un archivo se haya subido (la
        carpeta no existe como item consultable hasta entonces).
        """
        ruta_carpeta = "/".join([self.carpeta_base, "DebidaDiligencia", año, mes, identificacion_cliente])
        url = f"https://graph.microsoft.com/v1.0/users/{self.cuenta_onedrive}/drive/root:/{ruta_carpeta}"

        self.writer._refrescar_token()
        resp = requests.get(url, headers=self.writer.headers)

        if not resp.ok:
            print(f"    [OneDrive] No se pudo obtener el link de la carpeta ({resp.status_code}) - se deja la ruta local como respaldo.")
            return ""

        return resp.json().get("webUrl", "")