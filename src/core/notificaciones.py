"""
Notificación visual de Windows (toast) para avisar cuando el programa
necesita atención manual - principalmente captchas que no se pudieron
resolver automáticamente con 2Captcha.

Usa windows-toasts (no win10toast, que está en desuso y tiene problemas
de compatibilidad conocidos con versiones recientes de Python/Windows).

Diseñado para NUNCA tumbar el proceso de scraping si la notificación
falla por cualquier motivo (permisos, Windows sin soporte de toasts,
etc.) - un fallo aquí solo se imprime por consola, nunca lanza excepción
hacia quien llama.
"""

def notificar_atencion_manual(titulo: str, mensaje: str) -> None:
    """
    Muestra una notificación toast de Windows. Silenciosa ante
    cualquier fallo (librería no instalada, SO sin soporte, etc.) -
    el aviso por consola que ya existe en cada sitio sigue siendo el
    respaldo principal, esto es un extra, no un reemplazo.
    """
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("Lynx - PLAFT/UAFE")
        notificacion = Toast()
        notificacion.text_fields = [titulo, mensaje]
        toaster.show_toast(notificacion)
    except Exception as e:
        print(f"    [notificación] No se pudo mostrar el aviso de Windows: {type(e).__name__}: {e}")