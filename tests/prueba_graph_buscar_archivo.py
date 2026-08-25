"""
tests/prueba_graph_buscar_archivo.py

Busca el drive_id y item_id del Excel real en OneDrive (cuenta
unidadq@enlace.ec) via Microsoft Graph API, usando la busqueda por
nombre en vez de una ruta exacta (mas tolerante a que el archivo este
en cualquier carpeta de esa cuenta).

Requiere en el .env: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
(ya deberian estar). Imprime GRAPH_DRIVE_ID y GRAPH_EXCEL_ITEM_ID para
pegar directamente en el .env.
"""
import truststore
truststore.inject_into_ssl()

import msal
import requests

from config.settings import cargar_infra_config

NOMBRE_ARCHIVO = "Matriz Revisión Clientes.xlsx"


def main():
    infra = cargar_infra_config()

    faltantes = [
        nombre for nombre, valor in [
            ("AZURE_TENANT_ID", infra.azure_tenant_id),
            ("AZURE_CLIENT_ID", infra.azure_client_id),
            ("AZURE_CLIENT_SECRET", infra.azure_client_secret),
        ] if not valor
    ]
    if faltantes:
        print(f"Faltan estas variables en .env: {', '.join(faltantes)}")
        return

    app_msal = msal.ConfidentialClientApplication(
        client_id=infra.azure_client_id,
        authority=f"https://login.microsoftonline.com/{infra.azure_tenant_id}",
        client_credential=infra.azure_client_secret,
    )
    resultado_token = app_msal.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in resultado_token:
        print(f"No se pudo obtener el token: {resultado_token.get('error_description')}")
        return

    headers = {"Authorization": f"Bearer {resultado_token['access_token']}"}

    # Paso 1: obtener el drive_id del OneDrive de la cuenta
    print(f"Buscando el drive de {infra.cuenta_onedrive}...")
    resp_drive = requests.get(
        f"https://graph.microsoft.com/v1.0/users/{infra.cuenta_onedrive}/drive",
        headers=headers,
    )
    if resp_drive.status_code != 200:
        print(f"Error obteniendo el drive: {resp_drive.status_code} - {resp_drive.text}")
        return

    drive_id = resp_drive.json()["id"]
    print(f"GRAPH_DRIVE_ID={drive_id}")

    # Paso 2: buscar el archivo por nombre dentro de ese drive (no
    # requiere conocer la carpeta exacta)
    print(f"\nBuscando '{NOMBRE_ARCHIVO}'...")
    resp_buscar = requests.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/search(q='{NOMBRE_ARCHIVO}')",
        headers=headers,
    )
    if resp_buscar.status_code != 200:
        print(f"Error buscando el archivo: {resp_buscar.status_code} - {resp_buscar.text}")
        return

    coincidencias = resp_buscar.json().get("value", [])
    if not coincidencias:
        print(f"No se encontró ningún archivo llamado '{NOMBRE_ARCHIVO}' en ese drive.")
        return

    # La busqueda de Graph es difusa (por contenido, no solo nombre) -
    # se filtra por coincidencia EXACTA de nombre para descartar ruido.
    exactas = [item for item in coincidencias if item.get("name") == NOMBRE_ARCHIVO]

    if not exactas:
        print(f"\nSe encontraron {len(coincidencias)} resultados difusos, pero NINGUNO con el nombre EXACTO '{NOMBRE_ARCHIVO}'.")
        print("Revisa si el nombre real tiene alguna diferencia (mayusculas, espacios, extension).")
        return

    if len(exactas) > 1:
        print(f"\nOJO: hay {len(exactas)} archivos con el nombre EXACTO '{NOMBRE_ARCHIVO}'. Revisando rutas de cada uno...\n")
        candidatos = exactas
    else:
        candidatos = exactas

    for item in candidatos:
        # peticion de seguimiento para obtener parentReference.path -
        # los resultados de /search no siempre lo traen completo
        resp_detalle = requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item['id']}?$select=id,name,parentReference",
            headers=headers,
        )
        ruta = "?"
        if resp_detalle.status_code == 200:
            ruta = resp_detalle.json().get("parentReference", {}).get("path", "?")
        print(f"  - {item['name']} | id={item['id']} | ruta={ruta}")

    if len(candidatos) == 1:
        print(f"\nGRAPH_EXCEL_ITEM_ID={candidatos[0]['id']}")
    else:
        print("\nElige el que tenga la ruta 'COMPARTIDO/CUMPLIMIENTO' y copia su id como GRAPH_EXCEL_ITEM_ID.")


if __name__ == "__main__":
    main()