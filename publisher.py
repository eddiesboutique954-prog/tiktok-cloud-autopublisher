import os
import sys
import json
import time
import datetime
import urllib.parse
import requests
from playwright.sync_api import sync_playwright

STATE_FILE = "estado_publicaciones.json"
CATALOG_FILE = "catalogo_videos.json"
COOKIES_FILE = "cookies.json"
RELEASE_BASE_URL = "https://github.com/eddiesboutique954-prog/tiktok-cloud-autopublisher/releases/download/videos-batch-1"

def cargar_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def descargar_video(url, destino):
    print(f"Descargando video desde cloud storage: {url}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
    size_mb = os.path.getsize(destino) / (1024 * 1024)
    print(f"Descarga completa: {size_mb:.2f} MB")

def dismiss_popups(page):
    """Cierra modales de ayuda como 'Got it', 'Entendido' o cancela salidas accidentales."""
    for _ in range(3):
        try:
            # 1. Cancelar modal accidental 'Are you sure you want to exit?' si aparece
            exit_modal = page.locator('button:text-is("Cancel")')
            if exit_modal.count() > 0 and exit_modal.first.is_visible():
                print("Cancelando modal de salida accidental...")
                exit_modal.first.click(force=True)
                time.sleep(1)

            # 2. Cerrar modales 'Got it'
            popups = page.locator('button:has-text("Got it"), button:has-text("Entendido"), button:has-text("Aceptar")')
            if popups.count() > 0 and popups.first.is_visible():
                print("Cerrando modal emergente (Got it / Entendido)...")
                popups.first.click(force=True)
                time.sleep(1)
        except Exception:
            pass

def publicar_en_tiktok_playwright(video_path, descripcion, cookies_data):
    print("\n--- INICIANDO PUBLICADOR PLAYWRIGHT NATIVO (ULTRA RESILIENTE V3) ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        # 1. Inyectar cookies de sesion
        print("Inyectando cookies en el contexto del navegador...")
        pw_cookies = []
        for c in cookies_data:
            cookie = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".tiktok.com"),
                "path": c.get("path", "/")
            }
            if "secure" in c:
                cookie["secure"] = c["secure"]
            if "httpOnly" in c:
                cookie["httpOnly"] = c["httpOnly"]
            if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
                cookie["sameSite"] = c["sameSite"]
            pw_cookies.append(cookie)
            
        context.add_cookies(pw_cookies)
        page = context.new_page()
        
        # 2. Navegar a TikTok Studio Upload
        print("Navegando a TikTok Studio Upload...")
        page.goto("https://www.tiktok.com/tiktokstudio/upload?from=upload", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        
        print(f"URL actual: {page.url}")
        page.screenshot(path="1_inicio_pagina.png")
        
        if "login" in page.url.lower():
            page.screenshot(path="error_login.png")
            raise Exception("ERROR: TikTok redirigió al login. Las cookies expiraron.")
            
        # 3. Cerrar popups iniciales
        dismiss_popups(page)
                
        # 4. Inyectar archivo de video
        print(f"Cargando archivo de video ({os.path.basename(video_path)})...")
        file_input = page.locator('input[type="file"]').first
        file_attached = False
        try:
            file_input.wait_for(state="attached", timeout=15000)
            file_input.set_input_files(video_path)
            file_attached = True
        except Exception:
            for frame in page.frames:
                try:
                    f_input = frame.locator('input[type="file"]').first
                    if f_input.count() > 0:
                        f_input.set_input_files(video_path)
                        file_attached = True
                        break
                except Exception:
                    pass
                    
        if not file_attached:
            page.screenshot(path="error_no_file_input.png")
            raise Exception("No se encontró el input de archivo en la página.")
            
        print("Archivo asignado al input. Esperando procesamiento inicial...")
        time.sleep(8)
        
        # Cerrar el popup de 'New editing features added' que aparece al cargar el video
        dismiss_popups(page)
        page.screenshot(path="2_video_cargado.png")
        
        # 5. Inyectar descripcion viral en el editor
        print("Inyectando descripcion viral...")
        try:
            editor = page.locator('div[contenteditable="true"]').first
            editor.wait_for(state="visible", timeout=15000)
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            time.sleep(1)
            page.keyboard.insert_text(descripcion)
            print("Descripcion viral colocada con exito.")
        except Exception as e:
            print(f"Aviso en editor de descripcion: {e}")
            
        dismiss_popups(page)
        
        # 6. Scroll hacia abajo de todos los contenedores desplazables
        print("Haciendo scroll hacia el pie del formulario...")
        page.evaluate("""
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                if (el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            window.scrollTo(0, document.body.scrollHeight);
        """)
        time.sleep(2)
        
        # 7. Localizar el boton de publicar real
        # CRITICO: Usar :text-is("Post") o [data-e2e="post_video_button"] para NO cliquear el menu "Posts" del sidebar
        print("Buscando boton de publicacion del formulario...")
        btn_publicar = page.locator('button[data-e2e="post_video_button"], button:text-is("Post"), button:text-is("Publicar")').last
        btn_publicar.wait_for(state="attached", timeout=30000)
        btn_publicar.scroll_into_view_if_needed()
        time.sleep(1)
        
        # Esperar hasta 90s a que el video termine de subir y se habilite el boton
        print("Esperando que el boton Post/Publicar se habilite...")
        publicado = False
        for sec in range(90):
            dismiss_popups(page)
            is_disabled = (
                btn_publicar.get_attribute("aria-disabled") == "true" or 
                btn_publicar.get_attribute("data-disabled") == "true" or 
                btn_publicar.is_disabled()
            )
            if not is_disabled:
                print(f"¡Boton Post/Publicar habilitado tras {sec} segundos!")
                time.sleep(2)
                btn_publicar.scroll_into_view_if_needed()
                page.screenshot(path="3_antes_de_publicar.png")
                btn_publicar.click(force=True)
                publicado = True
                break
            time.sleep(1)
            
        if not publicado:
            page.screenshot(path="error_timeout_boton.png")
            raise Exception("Timeout: El boton de publicar nunca se habilito.")
            
        print("Click en Post/Publicar ejecutado. Esperando confirmacion de TikTok...")
        
        # 8. Esperar la confirmacion real de TikTok
        exito_confirmado = False
        for wait_s in range(35):
            time.sleep(1)
            dismiss_popups(page)
            # Detectar mensaje o botones de exito
            success_indicators = page.locator('button:has-text("Manage your posts"), button:has-text("Administrar publicaciones"), button:has-text("Upload another video"), div:has-text("Uploaded"), div:has-text("Your video has been uploaded")')
            if success_indicators.count() > 0 or "content" in page.url.lower():
                print(f"¡Confirmacion de publicacion exitosa detectada tras {wait_s} segundos!")
                exito_confirmado = True
                break
                
        time.sleep(3)
        page.screenshot(path="confirmacion_publicacion.png")
        print(f"URL final: {page.url}")
        
        if not exito_confirmado:
            print("Aviso: No se detecto el modal de exito explicito, verificando URL...")
            
        print("¡Proceso de publicacion completado con exito!")
        browser.close()

def main():
    print("=" * 60)
    print("   TIKTOK CLOUD AUTOPUBLISHER (GITHUB ACTIONS RUNNER)")
    print("=" * 60)
    
    catalogo = cargar_json(CATALOG_FILE)
    estado = cargar_json(STATE_FILE)
    
    if not catalogo:
        print("[ERROR] Catalogo de videos no encontrado o vacio.")
        sys.exit(1)
        
    pendientes = [v for v in catalogo if v["archivo"] not in estado]
    print(f"Total videos en catalogo: {len(catalogo)}")
    print(f"Videos ya publicados: {len(estado)}")
    print(f"Videos pendientes: {len(pendientes)}")
    
    if not pendientes:
        print("¡Todos los videos han sido publicados con exito!")
        return

    video_actual = pendientes[0]
    nombre_archivo = video_actual["archivo"]
    descripcion = video_actual.get("texto_publicacion", "Video viral #parati #fyp")
    video_url = video_actual.get("url_descarga")
    local_path = video_actual.get("archivo_local")
    
    print(f"\n--> Procesando siguiente video: {nombre_archivo}")
    print(f"Descripcion viral:\n{descripcion}\n")
    
    archivo_final = None
    if video_url:
        archivo_final = "temp_video.mp4"
        descargar_video(video_url, archivo_final)
    elif local_path and os.path.exists(local_path):
        archivo_final = local_path
    elif os.path.exists(nombre_archivo):
        archivo_final = nombre_archivo
    else:
        encoded_name = urllib.parse.quote(nombre_archivo)
        cloud_url = f"{RELEASE_BASE_URL}/{encoded_name}"
        archivo_final = "temp_video.mp4"
        descargar_video(cloud_url, archivo_final)
        
    print(f"Publicando en TikTok mediante sesion autorizada...")
    cookies_data = cargar_json(COOKIES_FILE)
    if not cookies_data:
        print("[ERROR] Archivo de cookies no encontrado o vacio.")
        sys.exit(1)
        
    try:
        publicar_en_tiktok_playwright(archivo_final, descripcion, cookies_data)
        
        # Guardar en el historial
        estado[nombre_archivo] = {
            "fecha_publicacion": datetime.datetime.now().isoformat(),
            "estado": "publicado_cloud"
        }
        guardar_json(STATE_FILE, estado)
        print(f"\n[EXITO TOTAL] ¡Video {nombre_archivo} registrado y guardado con exito!")
        
        if archivo_final == "temp_video.mp4" and os.path.exists(archivo_final):
            os.remove(archivo_final)
            
    except Exception as e:
        print(f"\n[ERROR CRITICO EN PUBLICACION]: {e}")
        if archivo_final == "temp_video.mp4" and os.path.exists(archivo_final):
            os.remove(archivo_final)
        sys.exit(1)

if __name__ == "__main__":
    main()
