import os
import sys
import json
import time
import datetime
import urllib.parse
import requests
from tiktok_uploader.upload import upload_video

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
        try:
            descargar_video(cloud_url, archivo_final)
        except Exception as e:
            print(f"[ERROR] No se pudo obtener el video ni local ni de la nube: {e}")
            sys.exit(1)
        
    print(f"Publicando en TikTok mediante sesion autorizada...")
    
    # Cargar cookies json
    cookies_data = cargar_json(COOKIES_FILE)
    
    try:
        upload_video(
            filename=archivo_final,
            description=descripcion,
            cookies_list=cookies_data if isinstance(cookies_data, list) else None,
            cookies=COOKIES_FILE if not isinstance(cookies_data, list) else None,
            browser="chromium",
            headless=True
        )
        print(f"\n[EXITO TOTAL] ¡Video {nombre_archivo} publicado con exito en TikTok!")
        
        # Guardar en el historial
        estado[nombre_archivo] = {
            "fecha_publicacion": datetime.datetime.now().isoformat(),
            "estado": "publicado_cloud"
        }
        guardar_json(STATE_FILE, estado)
        
        # Limpiar temporal
        if archivo_final == "temp_video.mp4" and os.path.exists(archivo_final):
            os.remove(archivo_final)
            
    except Exception as e:
        print(f"[ERROR EN SUBIDA]: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
