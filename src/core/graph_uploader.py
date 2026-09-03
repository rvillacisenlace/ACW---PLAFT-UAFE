"""
Sube archivos (PDFs, evidencia) a OneDrive vía Graph API, replicando la
misma estructura de carpetas que ya existe en local
(DebidaDiligencia/Año/Mes/Identificacion/.../archivo). El guardado
local sigue existiendo como respaldo/staging - esto es una copia
adicional, no un reemplazo.
"""
import os
import requests


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

    def subir_carpeta_cliente(self, carpeta_local_cliente: str, identificacion_cliente: str, año: str, mes: str) -> list[str]:
        """
        Sube TODOS los archivos dentro de la carpeta local de evidencia
        de un cliente, preservando la estructura completa de
        subcarpetas tal cual está en disco (sitio/archivo.pdf, o
        representante_legal_XXX/sitio/archivo.pdf si aplica) - no
        depende de que quien llame conozca cuantos niveles de anidacion
        hay, simplemente replica lo que encuentre.

        Devuelve la lista de nombres de archivo subidos exitosamente.
        Un archivo individual que falle se reporta por consola pero no
        detiene la subida del resto.
        """
        if not os.path.isdir(carpeta_local_cliente):
            return []

        # Se recolectan todos los archivos primero para poder mostrar
        # "X/Y" en el progreso, en vez de un conteo que crece sin saber
        # el total esperado.
        archivos_a_subir = []
        for raiz, _, archivos in os.walk(carpeta_local_cliente):
            for nombre_archivo in archivos:
                ruta_local = os.path.join(raiz, nombre_archivo)
                ruta_relativa = os.path.relpath(ruta_local, carpeta_local_cliente).replace(os.sep, "/")
                archivos_a_subir.append((ruta_local, ruta_relativa))

        total = len(archivos_a_subir)
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