import os
import sys
import json
import smtplib
import shutil
import traceback
from datetime import datetime, timedelta
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from shapely.geometry import shape, Point
from shapely.ops import transform

# Configurar matplotlib para que funcione sin pantalla (servidor)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import contextily as cx
from matplotlib.lines import Line2D

# Intentar importar librerías opcionales con seguridad
try:
    from pyproj import Transformer
except ImportError:
    Transformer = None
    print("⚠️ Advertencia: pyproj no está instalado. No se generarán mapas ni coordenadas GTM.", file=sys.stderr)

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    Document = None
    print("⚠️ Advertencia: python-docx no está instalado. No se generará el informe Word.", file=sys.stderr)

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

def convertir_a_gtm(lon, lat):
    """Convierte coordenadas de WGS84 (lat, lon) a GTM."""
    if not Transformer:
        return "No disponible"
    try:
        transformer = Transformer.from_crs(
            "EPSG:4326", 
            "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs",
            always_xy=True
        )
        gtm_x, gtm_y = transformer.transform(lon, lat)
        return f"{gtm_x:.2f} E, {gtm_y:.2f} N"
    except Exception as e:
        return "Error Calc"

def enviar_correo_alerta(cuerpo_html, asunto="🔥 Alerta Paxbán", imagen_mapa=None, archivo_zip=None):
    """Envía un correo electrónico de alerta."""
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = os.environ.get("SMTP_PORT")
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL]):
        print("❌ Error: Faltan credenciales de correo. Revise los Secrets de GitHub.", file=sys.stderr)
        return

    destinatarios = [email.strip() for email in RECIPIENT_EMAIL.split(',') if email.strip()]
    fecha_hora = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")
    asunto_completo = f"{asunto} - {fecha_hora}"

    print(f"📧 Enviando correo a: {', '.join(destinatarios)}")
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = asunto_completo
        
        msg.attach(MIMEText(cuerpo_html, 'html', 'utf-8'))
        
        if imagen_mapa:
            img = MIMEImage(imagen_mapa)
            img.add_header('Content-ID', '<mapa_peten>')
            img.add_header('Content-Disposition', 'inline', filename='mapa_peten.png')
            msg.attach(img)
            
        if archivo_zip:
            nombre_archivo, datos_archivo = archivo_zip
            part = MIMEApplication(datos_archivo, Name=nombre_archivo)
            part['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("✅ Correo enviado exitosamente.")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}", file=sys.stderr)

def enviar_alerta_telegram(mensaje, imagen_bytes=None):
    """Envía mensaje a Telegram."""
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_ID")

    if not all([BOT_TOKEN, CHAT_IDS_RAW]):
        return
    
    chat_ids = [cid.strip() for cid in CHAT_IDS_RAW.split(',') if cid.strip()]

    for chat_id in chat_ids:
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
        data = {'chat_id': chat_id, 'parse_mode': 'HTML'}
        files = None

        if imagen_bytes:
            api_url += "sendPhoto"
            files = {'photo': ('mapa.png', imagen_bytes, 'image/png')}
            data['caption'] = mensaje
        else:
            api_url += "sendMessage"
            data['text'] = mensaje

        try:
            if files:
                requests.post(api_url, data=data, files=files, timeout=20)
            else:
                requests.post(api_url, json=data, timeout=10)
        except Exception as e:
            print(f"⚠️ Error Telegram ({chat_id}): {e}", file=sys.stderr)

def guardar_mapa_local(imagen_bytes):
    """Guarda el mapa en la carpeta 2.4."""
    if not imagen_bytes: return
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    carpeta = os.path.join("2.4", fecha_dt.strftime("%Y"), fecha_dt.strftime("%m"))
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"Mapa_Calor_{fecha_dt.strftime('%Y-%m-%d')}.png")
    with open(ruta, "wb") as f: f.write(imagen_bytes)
    print(f"💾 Mapa guardado: {ruta}")

def guardar_bitacora(imagen_bytes, tipo, datos_puntos):
    """Guarda evidencia en bitácora."""
    if not imagen_bytes: return
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    carpeta = os.path.join("bitacora", fecha_dt.strftime("%Y"), fecha_dt.strftime("%m"), tipo)
    os.makedirs(carpeta, exist_ok=True)
    fecha_str = fecha_dt.strftime("%Y-%m-%d_%H%M")
    with open(os.path.join(carpeta, f"{tipo}_{fecha_str}.png"), "wb") as f: f.write(imagen_bytes)
    with open(os.path.join(carpeta, f"{tipo}_{fecha_str}.json"), "w", encoding="utf-8") as f:
        json.dump(datos_puntos, f, indent=2)

def generar_galeria_html():
    """Genera reportes.html."""
    try:
        mapas = []
        if os.path.exists("2.4"):
            for root, _, files in os.walk("2.4"):
                for file in files:
                    if file.endswith(".png"):
                        url = os.path.join(root, file).replace(os.sep, '/')
                        mapas.append({"url": url, "nombre": file, "fecha": file.replace("Mapa_Calor_", "").replace(".png", "")})
        
        mapas.sort(key=lambda x: x['fecha'], reverse=True)
        
        html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reportes Paxbán</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><div class="container py-5"><div class="d-flex justify-content-between align-items-center mb-4"><h1 class="text-success m-0">📂 Galería de Reportes</h1><a href="./" class="btn btn-outline-success">🏠 Inicio</a></div><div class="row row-cols-1 row-cols-md-3 g-4">"""
        for m in mapas:
            html += f"""<div class="col"><div class="card h-100 shadow-sm"><img src="{m['url']}" class="card-img-top" style="height:250px;object-fit:cover;"><div class="card-body"><h5 class="card-title">{m['fecha']}</h5><a href="{m['url']}" class="btn btn-primary btn-sm" download target="_blank">⬇️ Descargar</a></div></div></div>"""
        html += "</div></div></body></html>"
        
        with open("reportes.html", "w", encoding="utf-8") as f: f.write(html)
        print("✅ Galería HTML generada.")
    except Exception as e:
        print(f"❌ Error generando galería: {e}", file=sys.stderr)

def generar_mapa_imagen(puntos, concesiones=None):
    """Genera imagen PNG del mapa."""
    if not Transformer: return None
    try:
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        xs, ys, colores = [], [], []
        for p in puntos:
            x, y = transformer.transform(p['lon'], p['lat'])
            xs.append(x); ys.append(y); colores.append(p['color'])
        
        fig, ax = plt.subplots(figsize=(10, 10))
        
        if concesiones:
            for nombre, poly in concesiones.items():
                if "Paxbán" in nombre:
                    poly_3857 = transform(transformer.transform, poly)
                    if poly_3857.geom_type == 'Polygon':
                        x, y = poly_3857.exterior.xy
                        ax.plot(x, y, color='#2e7d32', linewidth=2, zorder=1)
                    elif poly_3857.geom_type == 'MultiPolygon':
                        for p in poly_3857.geoms:
                            x, y = p.exterior.xy
                            ax.plot(x, y, color='#2e7d32', linewidth=2, zorder=1)

        if xs: ax.scatter(xs, ys, c=colores, s=50, edgecolors='white', zorder=2)
        
        minx, miny = transformer.transform(-91.5, 15.8)
        maxx, maxy = transformer.transform(-89.0, 17.9)
        ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy)
        cx.add_basemap(ax, crs="EPSG:3857", source=cx.providers.Esri.NatGeoWorldMap, attribution=False)
        ax.set_axis_off()
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
        buf.seek(0); plt.close(fig)
        return buf.read()
    except Exception as e:
        print(f"⚠️ Error generando mapa: {e}", file=sys.stderr)
        return None

def crear_informe_word(ruta_salida, mes_str, anio, stats, img_ejemplo=None):
    if not Document: return
    try:
        doc = Document()
        doc.add_heading(f'INFORME MENSUAL - {mes_str} {anio}', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Incendios Paxbán: {stats['incendios']} | Pre-Alertas: {stats['pre_alertas']}")
        if img_ejemplo: doc.add_picture(img_ejemplo, width=Inches(6))
        doc.save(ruta_salida)
    except Exception as e:
        print(f"⚠️ Error creando Word: {e}", file=sys.stderr)

def generar_reporte_mensual():
    """Genera ZIP mensual."""
    print("📦 Iniciando generación de Reporte Mensual...")
    try:
        fecha_dt = datetime.utcnow() - timedelta(hours=6)
        anio, mes = fecha_dt.strftime("%Y"), fecha_dt.strftime("%m")
        nombre_mes = datetime.now().strftime("%B") # Simple
        
        raiz = f"Reporte_{mes}_{anio}"
        if os.path.exists(raiz): shutil.rmtree(raiz)
        os.makedirs(raiz)
        
        # Copiar carpetas
        for d in ["Reporte Diario", "Incendios Detectados", "Informe de Puntos de Calor"]:
            os.makedirs(os.path.join(raiz, d), exist_ok=True)
            
        # Copiar contenido 2.4
        src_diario = os.path.join("2.4", anio, mes)
        if os.path.exists(src_diario):
            for f in os.listdir(src_diario): shutil.copy2(os.path.join(src_diario, f), os.path.join(raiz, "Reporte Diario"))

        # Copiar alertas
        count_inc = 0
        src_alertas = os.path.join("bitacora", anio, mes, "alertas")
        if os.path.exists(src_alertas):
            for f in os.listdir(src_alertas): 
                if f.endswith(".png"): 
                    shutil.copy2(os.path.join(src_alertas, f), os.path.join(raiz, "Incendios Detectados"))
                    count_inc += 1

        # Word
        crear_informe_word(os.path.join(raiz, "Informe de Puntos de Calor", "Informe.docx"), mes, anio, {'incendios': count_inc, 'pre_alertas': 0})

        # ZIP
        zip_filename = f"Reporte_Mensual_{mes}_{anio}"
        shutil.make_archive(zip_filename, 'zip', root_dir='.', base_dir=raiz)
        
        # Mover a descargas
        os.makedirs("descargas", exist_ok=True)
        ruta_final = os.path.join("descargas", f"{zip_filename}.zip")
        if os.path.exists(ruta_final): os.remove(ruta_final) # Evitar error si existe
        shutil.move(f"{zip_filename}.zip", ruta_final)
        shutil.rmtree(raiz)
        
        print(f"✅ ZIP creado: {ruta_final}")
        
        with open(ruta_final, "rb") as f: zip_bytes = f.read()
        
        cuerpo = "<html><body><h2>📂 Reporte Mensual Listo</h2><p>Adjunto encontrará el reporte.</p></body></html>"
        enviar_correo_alerta(cuerpo, asunto=f"Reporte Mensual {mes}/{anio}", archivo_zip=(f"{zip_filename}.zip", zip_bytes))
        
    except Exception as e:
        print(f"❌ Error CRÍTICO en reporte mensual: {e}", file=sys.stderr)
        traceback.print_exc()

def cargar_concesiones():
    try:
        with open('concesiones1.geojson', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {f['properties'].get('Name', 'X'): shape(f['geometry']) for f in data['features']}
    except Exception as e:
        print(f"⚠️ Error cargando concesiones: {e}", file=sys.stderr)
        return {}

def main():
    print("🚀 Iniciando sistema Paxbán...")
    concesiones = cargar_concesiones()
    
    # Descargar datos NASA
    puntos = []
    
    # Configurar sesión con reintentos para mayor robustez
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    satelites = ["MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"]
    for sat in satelites:
        try:
            print(f"⬇️ Descargando datos de {sat}...")
            url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/-94,13.5,-88,20/3"
            res = session.get(url, timeout=60)
            if res.status_code == 200:
                lines = res.text.strip().split('\n')[1:]
                for line in lines:
                    try:
                        d = line.split(',')
                        lat, lon = float(d[0]), float(d[1])
                        p = Point(lon, lat)
                        
                        # Verificar si está en Paxbán
                        en_paxban = False
                        for nom, poly in concesiones.items():
                            if "Paxbán" in nom and poly.contains(p):
                                en_paxban = True
                                break
                        
                        # Calcular antigüedad
                        dt = datetime.strptime(f"{d[5]} {d[6]}", "%Y-%m-%d %H%M")
                        horas = (datetime.utcnow() - dt).total_seconds() / 3600
                        color = "red" if horas <= 24 else "orange" if horas <= 48 else "yellow"
                        
                        puntos.append({
                            "lat": lat, "lon": lon, "color": color, "alerta": en_paxban,
                            "sat": sat, "fecha": f"{d[5]} {d[6]}", "horas": horas,
                            "concesion": "Paxbán" if en_paxban else "Externa",
                            "gtm": convertir_a_gtm(lon, lat)
                        })
                    except: pass
        except Exception as e:
            print(f"⚠️ Error descargando {sat}: {e}", file=sys.stderr)

    if not puntos:
        print("⚠️ Advertencia: No se encontraron datos de incendios en el área seleccionada.")

    # Guardar JSON para la web
    with open('incendios.json', 'w') as f: json.dump(puntos, f)
    
    alertas = [p for p in puntos if p['alerta']]
    force_report = os.environ.get("FORCE_REPORT", "false") == "true"
    
    # Generar mapa si es necesario
    img_bytes = None
    if alertas or force_report:
        img_bytes = generar_mapa_imagen(puntos, concesiones)
        if force_report: guardar_mapa_local(img_bytes)
        if alertas: guardar_bitacora(img_bytes, "alertas", alertas)

    # Enviar Alertas
    if alertas:
        msg = f"🔥 <b>ALERTA PAXBÁN</b>\nSe detectaron {len(alertas)} incendios."
        enviar_alerta_telegram(msg, img_bytes)
        html = f"<h2>🔥 Alerta de Incendio</h2><p>Se detectaron {len(alertas)} focos.</p>"
        if img_bytes: html += '<img src="cid:mapa_peten">'
        enviar_correo_alerta(html, imagen_mapa=img_bytes)
        
    elif force_report:
        msg = f"✅ <b>Reporte Diario</b>\nSin amenazas activas.\nPuntos analizados: {len(puntos)}"
        enviar_alerta_telegram(msg, img_bytes)
        html = f"<h2>✅ Reporte Diario</h2><p>Sin amenazas activas.</p>"
        if img_bytes: html += '<img src="cid:mapa_peten">'
        html += '<br><a href="https://JR23CR.github.io/alerta-paxban/reportes.html">📂 Ver Galería</a>'
        enviar_correo_alerta(html, asunto="Reporte Diario", imagen_mapa=img_bytes)

    # Generar Galería SIEMPRE
    generar_galeria_html()

    # Reporte Mensual si se solicita
    if os.environ.get("ACTION_TYPE") == "reporte_mensual":
        generar_reporte_mensual()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("❌ ERROR FATAL EN EL SCRIPT:", file=sys.stderr)
        traceback.print_exc()
        # No salimos con error para permitir que GitHub Pages intente desplegar lo que haya
        sys.exit(0) 
