# -*- mode: python ; coding: utf-8 -*-
"""
Spec de PyInstaller para Lynx (ACW-PLAFT-UAFE).

Puntos delicados que este spec resuelve explícitamente:

1. Playwright trae su propio "driver" (un ejecutable Node.js + código
   JS en playwright/driver/) que NO son imports de Python, así que
   PyInstaller nunca los detecta por análisis estático - hay que
   copiarlos a mano como datas, preservando la ruta relativa exacta
   dentro del paquete "playwright" para que en tiempo de ejecución el
   paquete los siga encontrando en el mismo lugar relativo de siempre.

2. windows-toasts usa paquetes "winrt-*" (bindings nativos de Windows
   Runtime, no python puro) - se agregan como hidden imports porque
   PyInstaller no siempre los detecta bien al ser generados
   dinámicamente.

3. El Excel plantilla (templates/) se empaqueta como dato, para que
   LocalExcelWriter (si algún día se usa en vez de GraphAPIWriter)
   tenga algo que abrir sin depender de que exista en disco aparte.

NOTA IMPORTANTE, sin confirmar todavía (Fase 5 recién arrancando,
nunca se generó un .exe de este proyecto antes de hoy): es MUY
probable que la primera corrida de "pyinstaller lynx.spec" falle o el
.exe resultante truene al abrir, por dependencias que este spec no
anticipó correctamente (winrt/windows-toasts y truststore son las más
propensas a dar problemas con PyInstaller, por experiencia general con
paquetes que usan extensiones nativas/COM). Se espera iterar sobre
esto con los errores reales que aparezcan.
"""
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# --- Localizar el driver de Playwright para copiarlo completo ---
import playwright
ruta_playwright = os.path.dirname(playwright.__file__)
ruta_driver_playwright = os.path.join(ruta_playwright, "driver")

datas = [
    (ruta_driver_playwright, "playwright/driver"),
    ("templates", "templates"),
    ("assets", "assets"),
]

hiddenimports = [
    # windows-toasts / winrt - paquetes con bindings nativos, PyInstaller
    # no siempre los detecta bien por análisis estático.
    "winrt.windows.data.xml.dom",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.ui.notifications",
    "windows_toasts",
    # truststore usa ctypes para el almacen de certificados del SO -
    # a veces PyInstaller no detecta bien los submódulos internos.
    "truststore",
]

# collect_all() para playwright asegura que TODOS sus submódulos
# internos (sync_api, async_api, _impl, etc.) se incluyan, no solo los
# que PyInstaller detecte por analisis estatico del codigo de main.py.
datas_pw, binaries_pw, hiddenimports_pw = collect_all("playwright")
datas += datas_pw
hiddenimports += hiddenimports_pw

# Lo mismo para playwright_stealth: trae archivos .js propios en
# playwright_stealth/js/ que se leen en tiempo de ejecucion (no son
# imports de Python, PyInstaller no los detecta solo) - confirmado con
# evidencia real (2026-09-10): sin esto, el .exe truena al arrancar con
# "FileNotFoundError: ...playwright_stealth\js\generate.magic.arrays.js".
datas_stealth, binaries_stealth, hiddenimports_stealth = collect_all("playwright_stealth")
datas += datas_stealth
binaries_pw += binaries_stealth
hiddenimports += hiddenimports_stealth

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=binaries_pw,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Lynx",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=True es OBLIGATORIO - el programa usa input() en varios
    # puntos (captchas manuales), una app "windowed" (console=False) no
    # tiene terminal donde el usuario pueda escribir esas respuestas.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/lynx_icono.ico",
)
