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

def publicar_en_tiktok_playwright(video_path, descripcion, cookies_data):
    print("\n--- INICIANDO PUBLICADOR PLAYWRIGHT NATIVO ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
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
        page.goto("https://www.tiktok.com/tiktokstudio/upload?from=upload", wait_until="networkidle", timeout=60000)
        time.sleep(5)
        
        print(f"URL actual: {page.url}")
        if "login" in page.url.lower():
            page.screenshot(path="error_login.png")
            raise Exception("ERROR: TikTok redirigió al login. Las cookies pueden haber expirado.")
            
        # 3. Cerrar popups iniciales si existen
        for _ in range(3):
            try:
                btn_popup = page.locator('div[role="dialog"] button, button:has-text("Entendido"), button:has-text("Aceptar")').first
                if btn_popup.is_visible():
                    btn_popup.click()
                    time.sleep(1)
            except Exception:
                pass
                
        # 4. Inyectar archivo de video
        print(f"Cargando archivo de video ({os.path.basename(video_path)})...")
        file_input = page.locator('input[type="file"]')
        file_input.wait_for(state="attached", timeout=30000)
        file_input.set_input_files(video_path)
        print("Archivo asignado al input. Esperando procesamiento inicial...")
        time.sleep(8)
        
        # 5. Inyectar descripcion viral
        print("Inyectando descripcion viral...")
        try:
            editor = page.locator('div[contenteditable="true"]').first
            editor.wait_for(state="visible", timeout=15000)
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.insert_text(descripcion)
            print("Descripcion colocada con exito.")
        except Exception as e:
            print(f"Aviso en editor de descripcion: {e}")
            
        # 6. Scroll hacia abajo para ver opciones y boton Publicar
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        
        # 7. Buscar boton de Publicar / Post
        print("Buscando boton de publicacion...")
        btn_publicar = page.locator('button:has-text("Publicar"), button:has-text("Post"), button[data-e2e="post_video_button"]').first
        btn_publicar.wait_for(state="attached", timeout=30000)
        
        # Esperar a que el video termine de subir (boton deje de estar deshabilitado)
        print("Esperando que TikTok termine de procesar el video...")
        publicado = False
        for sec in range(90):
            is_disabled = (
                btn_publicar.get_attribute("aria-disabled") == "true" or 
                btn_publicar.get_attribute("data-disabled") == "true" or 
                btn_publicar.is_disabled()
            )
            if not is_disabled:
                print(f"¡Boton de publicacion habilitado tras {sec} segundos!")
                time.sleep(2)
                btn_publicar.scroll_into_view_if_needed()
                btn_publicar.click(force=True)
                publicado = True
                break
            time.sleep(1)
            
        if not publicado:
            page.screenshot(path="error_timeout_boton.png")
            raise Exception("Timeout: El boton de publicar nunca se habilito.")
            
        print("Click en Publicar realizado. Esperando confirmacion de TikTok...")
        time.sleep(12)
        
        # Tomar captura final de confirmacion
        page.screenshot(path="confirmacion_publicacion.png")
        print(f"URL tras publicar: {page.url}")
        
        # Verificar que no estemos en un error
        if "error" in page.url.lower():
            raise Exception("TikTok devolvio una URL de error tras publicar.")
            
        print("¡Video publicado exitosamente en TikTok!")
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
        
    # Filtrar videos que no han sido publicados
    pendientes = [v for v in catalogo if v["archivo"] not in estado]
    print(f"Total videos en catalogo: {len(catalogo)}")
    print(f"Videos ya publicados: {len(estado)}")
    print(f"Videos pendientes: {len(pendientes)}")
    
    if not pendientes:
        print("¡Todos los videos han sido publicados con exito!")
        return

    # Tomar el siguiente video en turno
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
        # Fallback a release de GitHub
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
        
        # Guardar en el historial SOLO si termino sin excepcion
        estado[nombre_archivo] = {
            "fecha_publicacion": datetime.datetime.now().isoformat(),
            "estado": "publicado_cloud"
        }
        guardar_json(STATE_FILE, estado)
        print(f"\n[EXITO TOTAL] ¡Video {nombre_archivo} registrado y guardado con exito!")
        
        # Limpiar temporal
        if archivo_final == "temp_video.mp4" and os.path.exists(archivo_final):
            os.remove(archivo_final)
            
    except Exception as e:
        print(f"\n[ERROR CRITICO EN PUBLICACION]: {e}")
        # Limpiar temporal si fallo
        if archivo_final == "temp_video.mp4" and os.path.exists(archivo_final):
            os.remove(archivo_final)
        # Salir con error para que GitHub Actions alerte y no guarde en estado
        sys.exit(1)

if __name__ == "__main__":
    main()
