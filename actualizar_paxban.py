import os
import sys
import json
import smtplib
import shutil
import traceback
import math
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
from shapely.ops import transform, nearest_points

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

MESES_ES = {
    "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
    "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
    "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
}

CAMPAMENTOS = [
    {"nombre": "Paxbán", "x": 541459.545, "y": 1968309.168},
    {"nombre": "El Guiro", "x": 546526.26, "y": 1966445.116},
    {"nombre": "Las corrientes", "x": 548522.604, "y": 1963905.742},
    {"nombre": "El Carrizal", "x": 549089.113, "y": 1960904.892},
    {"nombre": "Los campitos", "x": 542354.499, "y": 1962816.912},
    {"nombre": "Ojo de agua", "x": 539679.072, "y": 1960737.306},
    {"nombre": "El Tiempo", "x": 544849.236, "y": 1958376.547},
    {"nombre": "La Reforma", "x": 528989.788, "y": 1963524.435},
    {"nombre": "El Magueyal", "x": 526593.273, "y": 1967097.684},
    {"nombre": "El Mapache", "x": 520451.541, "y": 1965656.699},
    {"nombre": "La Pepesca", "x": 517819.874, "y": 1968240.009},
    {"nombre": "La Lagartija", "x": 517181.659, "y": 1969837.431},
    {"nombre": "El Salmoncito", "x": 517084.743, "y": 1963131.811},
    {"nombre": "El Salmon", "x": 517084.743, "y": 1962568.742},
    {"nombre": "Santa Elena", "x": 518382.504, "y": 1957356.105},
    {"nombre": "El Infiernon", "x": 521941.396, "y": 1953847.365},
    {"nombre": "La Isla", "x": 523325.068, "y": 1952239.194},
    {"nombre": "El Morgan", "x": 524265.663, "y": 1945609.637},
    {"nombre": "El Infiernito", "x": 529602.392, "y": 1954204.481},
    {"nombre": "El Jobal", "x": 536158.163, "y": 1966152.753},
    {"nombre": "Los Cuyos", "x": 533886.902, "y": 1957284.17},
    {"nombre": "El Recreo", "x": 537205.586, "y": 1965649.189},
    {"nombre": "Los Cuyos II", "x": 539968.134, "y": 1962862.671},
    {"nombre": "Los Perros", "x": 534691.126, "y": 1960808.64}
]

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

def calcular_distancia_direccion(p, poly):
    """Calcula distancia y dirección desde un punto al polígono."""
    if not Transformer: return None
    try:
        # Proyección GTM para metros (EPSG:4326 -> GTM)
        proj_gtm_str = "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
        trans_to_meter = Transformer.from_crs("EPSG:4326", proj_gtm_str, always_xy=True)
        
        p_meter = transform(trans_to_meter.transform, p)
        poly_meter = transform(trans_to_meter.transform, poly)
        
        dist_meters = poly_meter.distance(p_meter)
        p_near = nearest_points(poly_meter, p_meter)[0]
        
        dx = p_meter.x - p_near.x
        dy = p_meter.y - p_near.y
        angle = math.degrees(math.atan2(dy, dx))
        
        if -45 <= angle <= 45: direction = "Este"
        elif 45 < angle <= 135: direction = "Norte"
        elif -135 <= angle < -45: direction = "Sur"
        else: direction = "Oeste"
        
        return f"{int(dist_meters)} metros del límite {direction}"
    except Exception:
        return None

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
        
        # Adjuntar logo
        try:
            with open('logo (2).png', 'rb') as f:
                logo_img = MIMEImage(f.read())
                logo_img.add_header('Content-ID', '<logo_paxban>')
                msg.attach(logo_img)
        except FileNotFoundError:
            print("⚠️ Advertencia: No se encontró logo (2).png. El correo se enviará sin logo.", file=sys.stderr)

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
        
        # Buscar reportes mensuales (ZIPs)
        reportes_mensuales = []
        if os.path.exists("descargas"):
            for root, _, files in os.walk("descargas"):
                for file in files:
                    if file.endswith(".zip"):
                        url = os.path.join(root, file).replace(os.sep, '/')
                        
                        # Intentar crear un nombre bonito para la tarjeta (Ej: "Enero 2026")
                        nombre_mostrar = file
                        try:
                            # Formato esperado: Reporte_Mensual_01_2026.zip
                            parts = file.replace(".zip", "").split("_")
                            if len(parts) >= 4:
                                mes_num = parts[2]
                                anio = parts[3]
                                mes_nom = MESES_ES.get(mes_num, mes_num)
                                nombre_mostrar = f"{mes_nom} {anio}"
                        except: pass
                        
                        reportes_mensuales.append({"url": url, "nombre": nombre_mostrar, "filename": file})
        
        print(f"📦 Se encontraron {len(reportes_mensuales)} reportes mensuales.")
        # Ordenar por nombre de archivo original para mantener orden cronológico
        reportes_mensuales.sort(key=lambda x: x['filename'], reverse=True)

        html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reportes Paxbán</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><div class="container py-5"><div class="d-flex justify-content-between align-items-center mb-4"><h1 class="text-success m-0">📂 Galería de Reportes</h1><a href="./" class="btn btn-outline-success">🏠 Inicio</a></div>"""
        
        # Sección Reportes Mensuales
        if reportes_mensuales:
            html += """<h3 class="text-secondary mt-4 border-bottom pb-2">📦 Reportes Mensuales (Descarga Completa)</h3><div class="row row-cols-1 row-cols-md-3 g-4 mb-5">"""
            for r in reportes_mensuales:
                html += f"""<div class="col"><div class="card h-100 shadow-sm border-success"><div class="card-body text-center"><h5 class="card-title text-success">📅 {r['nombre']}</h5><p class="card-text small text-muted">Incluye: Reportes diarios, Incendios y Word.</p><a href="{r['url']}" class="btn btn-success w-100" download>⬇️ Descargar ZIP</a></div></div></div>"""
            html += "</div>"

        # Sección Mapas Diarios
        html += """<h3 class="text-secondary mt-4 border-bottom pb-2">🗺️ Mapas Diarios</h3><div class="row row-cols-1 row-cols-md-3 g-4">"""
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
                            
        # Plotear Campamentos (Casitas)
        if CAMPAMENTOS:
            gtm_proj = "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            trans_gtm_to_3857 = Transformer.from_crs(gtm_proj, "EPSG:3857", always_xy=True)
            
            camp_xs, camp_ys = [], []
            for camp in CAMPAMENTOS:
                cx, cy = trans_gtm_to_3857.transform(camp['x'], camp['y'])
                camp_xs.append(cx)
                camp_ys.append(cy)
                ax.text(cx, cy - 1500, camp['nombre'], fontsize=7, ha='center', va='top', color='black', fontweight='bold', bbox=dict(facecolor='white', alpha=0.6, edgecolor='none', pad=0.5), zorder=4)
            
            ax.scatter(camp_xs, camp_ys, c='#795548', s=90, marker='p', edgecolors='white', linewidth=1, zorder=4, label='Campamentos')

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
        nombre_mes = MESES_ES.get(mes, mes)
        
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
        
        # Mover a descargas organizado por Año/Mes (Nombre)
        carpeta_destino = os.path.join("descargas", anio, nombre_mes)
        os.makedirs(carpeta_destino, exist_ok=True)
        ruta_final = os.path.join(carpeta_destino, f"{zip_filename}.zip")
        if os.path.exists(ruta_final): os.remove(ruta_final) # Evitar error si existe
        shutil.move(f"{zip_filename}.zip", ruta_final)
        shutil.rmtree(raiz)
        
        print(f"✅ ZIP creado: {ruta_final}")
        
        with open(ruta_final, "rb") as f: zip_bytes = f.read()
        
        cuerpo = f"""
        <html><head><style>
            @media print {{
                @page {{ margin: 0.5cm; }} 
                body {{ font-family: Arial, sans-serif; font-size: 9pt; }} 
                h2 {{ color: #1565C0; margin-top: 0; font-size: 12pt; margin-bottom: 5px; }}
                .info-box {{ background-color: #e3f2fd !important; border-left: 5px solid #1565C0 !important; -webkit-print-color-adjust: exact; padding: 5px !important; margin: 5px 0 !important; }}
                table {{ margin-bottom: 5px !important; }}
                td {{ padding-bottom: 0 !important; }}
                .no-print {{ display: none; }}
            }}
        </style></head><body>
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <table style="width: 100%; border-bottom: 2px solid #1565C0; margin-bottom: 15px;">
                <tr>
                    <td style="width: 100px; padding-bottom: 10px;">
                        <img src="cid:logo_paxban" alt="Logo Paxbán" style="width: 90px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 10px;">
                        <h2 style="color: #1565C0; margin: 0;">📦 Reporte Mensual Generado: {nombre_mes} {anio}</h2>
                    </td>
                </tr>
            </table>
            <p>Estimado usuario,</p>
            <p>Se ha completado la compilación del reporte mensual de monitoreo satelital.</p>

            <div class="info-box" style="background-color: #e3f2fd; padding: 15px; border-left: 5px solid #1565C0; margin: 20px 0;">
                <h3 style="margin: 0; color: #0d47a1;">Archivo Adjunto: {zip_filename}.zip</h3>
                <p style="margin: 5px 0 0 0;">El archivo ZIP adjunto contiene las siguientes carpetas:</p>
                <ul style="margin-top: 10px; padding-left: 20px;">
                    <li><strong>Reporte Diario:</strong> Todos los mapas de calor diarios del mes.</li>
                    <li><strong>Incendios Detectados:</strong> Evidencia de alertas de incendio (si las hubo).</li>
                    <li><strong>Informe de Puntos de Calor:</strong> Documento Word con el resumen.</li>
                </ul>
            </div>

            <p>Puede descargar el archivo directamente desde este correo.</p>
            <br><hr style="border: 0; border-top: 1px solid #eee;">
            <div style="font-size: 12px; color: #666;">
                <p><b>Sistema de Alerta Temprana Paxbán</b><br>Mensaje generado automáticamente.<br>Desarrollado por JR23CR</p>
                <p style="text-align: center;" class="no-print"><a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #1565C0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">📂 Ir a la Galería de Reportes</a></p>
            </div>
        </div>
        </body></html>"""
        enviar_correo_alerta(cuerpo, asunto=f"Reporte Mensual {nombre_mes} {anio}", archivo_zip=(f"{zip_filename}.zip", zip_bytes))
        
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
    action_type = os.environ.get("ACTION_TYPE", "monitor")
    
    puntos = []
    
    # --- LÓGICA DE PRUEBAS (SIMULACROS) ---
    if action_type.startswith("test_"):
        print(f"🧪 MODO PRUEBA ACTIVADO: {action_type}")
        fecha_sim = datetime.utcnow().strftime("%Y-%m-%d %H%M")
        
        if action_type == "test_incendio":
            # Punto DENTRO de Paxbán
            puntos.append({
                "lat": 17.7, "lon": -90.15, "color": "red", "alerta": True, "pre_alerta": False,
                "sat": "SIMULACRO", "fecha": fecha_sim, "horas": 1,
                "concesion": "Paxbán", "gtm": convertir_a_gtm(-90.15, 17.7)
            })
        elif action_type == "test_prealerta":
            # Punto CERCA de Paxbán (Zona de Amortiguamiento)
            lat, lon = 17.55, -90.2
            p_test = Point(lon, lat)
            dist_info_test = "Zona de Amortiguamiento"
            
            # Calcular dinámicamente usando el polígono real
            for nom, poly in concesiones.items():
                if "Paxbán" in nom:
                    res = calcular_distancia_direccion(p_test, poly)
                    if res: dist_info_test = res
                    break
            
            puntos.append({
                "lat": lat, "lon": lon, "color": "orange", "alerta": False, "pre_alerta": True,
                "sat": "SIMULACRO", "fecha": fecha_sim, "horas": 12,
                "concesion": "Zona de Amortiguamiento", "gtm": convertir_a_gtm(lon, lat),
                "dist_info": dist_info_test
            })
        elif action_type == "test_monitoreo":
            # Sin puntos, solo fuerza el reporte verde
            pass
            
    # --- LÓGICA NORMAL (DESCARGA NASA) ---
    else:
        # Configurar sesión con reintentos para mayor robustez
        session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        satelites = ["MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        for sat in satelites:
            try:
                print(f"⬇️ Descargando datos de {sat}...")
                url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/-94,13.5,-88,20/3"
                res = session.get(url, headers=headers, timeout=60)
                if res.status_code == 200:
                    lines = res.text.strip().split('\n')[1:]
                    for line in lines:
                        try:
                            d = line.split(',')
                            lat, lon = float(d[0]), float(d[1])
                            p = Point(lon, lat)
                            
                            # Verificar ubicación
                            en_paxban = False
                            en_prealerta = False
                            concesion_nombre = "Externa"
                            dist_info = None
                            
                            for nom, poly in concesiones.items():
                                if "Paxbán" in nom:
                                    if poly.contains(p):
                                        en_paxban = True
                                        concesion_nombre = "Paxbán"
                                        break
                                    # Buffer aproximado de 10km (0.09 grados)
                                    elif poly.distance(p) < 0.09:
                                        en_prealerta = True
                                        concesion_nombre = "Zona de Amortiguamiento"
                                        dist_info = calcular_distancia_direccion(p, poly)
                            
                            # Calcular antigüedad
                            dt = datetime.strptime(f"{d[5]} {d[6]}", "%Y-%m-%d %H%M")
                            horas = (datetime.utcnow() - dt).total_seconds() / 3600
                            color = "red" if horas <= 24 else "orange" if horas <= 48 else "yellow"
                            
                            puntos.append({
                                "lat": lat, "lon": lon, "color": color, "alerta": en_paxban, "pre_alerta": en_prealerta,
                                "sat": sat, "fecha": f"{d[5]} {d[6]}", "horas": horas,
                                "concesion": concesion_nombre,
                                "gtm": convertir_a_gtm(lon, lat),
                                "dist_info": dist_info
                            })
                        except: pass
            except Exception as e:
                print(f"⚠️ Error descargando {sat}: {e}", file=sys.stderr)

        if not puntos:
            print("⚠️ Advertencia: No se encontraron datos de incendios en el área seleccionada.")

    # Guardar JSON para la web
    with open('incendios.json', 'w') as f: json.dump(puntos, f)
    
    # --- GUARDAR CAMPAMENTOS PARA LA WEB ---
    if Transformer:
        try:
            # Convertir GTM a Lat/Lon (WGS84) para el mapa web
            gtm_proj = "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            trans_gtm_to_wgs84 = Transformer.from_crs(gtm_proj, "EPSG:4326", always_xy=True)
            
            campamentos_web = []
            for c in CAMPAMENTOS:
                lon, lat = trans_gtm_to_wgs84.transform(c['x'], c['y'])
                campamentos_web.append({
                    "nombre": c['nombre'],
                    "lat": lat,
                    "lon": lon
                })
            
            with open('campamentos.json', 'w') as f: json.dump(campamentos_web, f)
            print("✅ campamentos.json generado correctamente.")
        except Exception as e:
            print(f"⚠️ Error exportando campamentos: {e}", file=sys.stderr)

    alertas = [p for p in puntos if p['alerta']]
    pre_alertas = [p for p in puntos if p.get('pre_alerta')]
    force_report = os.environ.get("FORCE_REPORT", "false") == "true"
    
    # Generar mapa si es necesario
    img_bytes = None
    if alertas or pre_alertas or force_report:
        img_bytes = generar_mapa_imagen(puntos, concesiones)
        if force_report: guardar_mapa_local(img_bytes)
        if alertas: guardar_bitacora(img_bytes, "alertas", alertas)

    # --- ENVIAR CORREOS SEGÚN PRIORIDAD ---
    
    # 1. ALERTA ROJA (Incendio DENTRO de Paxbán)
    if alertas:
        msg = f"🔥 <b>ALERTA PAXBÁN</b>\n"
        msg += f"<b>Se detectaron {len(alertas)} incendios activos.</b>\n"
        for i, p in enumerate(alertas):
            msg += f"\n🔴 <b>Foco {i+1}:</b>"
            msg += f"\n📍 {p['lat']:.5f}, {p['lon']:.5f}"
            msg += f"\n🗺️ GTM: {p['gtm']}"
            msg += f"\n🛰️ {p['sat']} - {p['fecha']}"
        enviar_alerta_telegram(msg, img_bytes)
        
        html = f"""
        <html>
        <head>
        <style>
            @media print {{
                @page {{ margin: 0.5cm; }}
                body {{ font-family: Arial, sans-serif; font-size: 9pt; }}
                h2 {{ color: #D32F2F; margin-top: 0; font-size: 12pt; margin-bottom: 5px; }}
                .alert-box {{ background-color: #ffcdd2 !important; border-left: 5px solid #D32F2F !important; -webkit-print-color-adjust: exact; padding: 5px !important; margin: 5px 0 !important; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 5px !important; }}
                th {{ background-color: #ef5350 !important; color: white !important; -webkit-print-color-adjust: exact; padding: 2px; }}
                td {{ padding: 2px; border: 1px solid #ddd; }}
                img {{ max-height: 300px !important; width: auto; display: block; margin: 5px auto; }}
                .no-print {{ display: none; }}
            }}
        </style>
        </head>
        <body>
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <table style="width: 100%; border-bottom: 2px solid #D32F2F; margin-bottom: 10px;">
                <tr>
                    <td style="width: 80px; padding-bottom: 5px;">
                        <img src="cid:logo_paxban" alt="Logo Paxbán" style="width: 70px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 5px;">
                        <h2 style="color: #D32F2F; margin: 0; font-size: 18pt;">🔥 ALERTA DE INCENDIO DETECTADO 🔥</h2>
                    </td>
                </tr>
            </table>
            <p style="margin: 5px 0;">Estimado usuario,</p>
            <p style="margin: 5px 0;"><strong>¡Atención!</strong> El sistema Alerta Paxbán ha identificado <strong>{len(alertas)} foco(s) de incendio activos</strong> dentro de los polígonos de las concesiones monitoreadas.</p>
            <div class="alert-box" style="background-color: #ffcdd2; padding: 10px; border-left: 5px solid #D32F2F; margin: 10px 0;">
                <h3 style="margin: 0; color: #b71c1c; font-size: 14pt;">Resumen de la Alerta</h3>
                <p style="margin: 5px 0 0 0;">Se requiere verificación y acción inmediata.</p>
            </div>
            <h4 style="color: #333; margin: 10px 0 5px 0;">Detalles de los Focos Detectados:</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <tr style="background-color: #ef5350; color: white; text-align: left;">
                    <th style="padding: 5px; border: 1px solid #ddd;">#</th><th style="padding: 5px; border: 1px solid #ddd;">Coordenadas</th><th style="padding: 5px; border: 1px solid #ddd;">GTM</th><th style="padding: 5px; border: 1px solid #ddd;">Fecha/Hora (UTC)</th><th style="padding: 5px; border: 1px solid #ddd;">Satélite</th>
                </tr>"""
        for i, p in enumerate(alertas):
            html += f"""
            <tr style="background-color: {'#ffebee' if i % 2 == 0 else '#ffffff'}; font-size: 11px;">
                <td style="padding: 4px; border: 1px solid #ddd;">{i+1}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['lat']:.4f}, {p['lon']:.4f}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['gtm']}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['fecha']}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['sat']}</td>
            </tr>"""
        html += "</table>"
        html += '<p style="margin: 10px 0 5px 0;">A continuación se presenta el mapa de la situación:</p>'
        if img_bytes: html += '<br><img src="cid:mapa_peten" style="max-width: 100%; max-height: 350px; height: auto; border: 1px solid #ddd; border-radius: 5px; display: block; margin: 0 auto;"><br>'
        html += f"""<br><hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;"><div style="font-size: 11px; color: #666;"><p style="margin: 2px 0;"><b>Sistema de Alerta Temprana Paxbán</b><br>Mensaje generado por detección de amenaza.<br>Desarrollado por JR23CR</p><p style="text-align: center; margin-top: 10px;" class="no-print"><a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #D32F2F; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px;">📂 Ver Galería de Reportes</a></p></div></div></body></html>"""
        enviar_correo_alerta(html, asunto="🔥 ALERTA DE INCENDIO - Paxbán", imagen_mapa=img_bytes)
        
    # 2. PRE-ALERTA AMARILLA (Incendio CERCA de Paxbán)
    elif pre_alertas:
        print(f"📧 Enviando Pre-Alerta por {len(pre_alertas)} focos...")
        msg = f"⚠️ <b>PRE-ALERTA PAXBÁN</b>\n"
        msg += f"<b>Actividad en zona de amortiguamiento ({len(pre_alertas)} focos).</b>\n"
        for i, p in enumerate(pre_alertas):
            msg += f"\n🟠 <b>Foco {i+1}:</b>"
            if p.get('dist_info'):
                msg += f"\n📏 {p['dist_info']}"
            msg += f"\n📍 {p['lat']:.5f}, {p['lon']:.5f}"
            msg += f"\n🗺️ GTM: {p['gtm']}"
            msg += f"\n🛰️ {p['sat']} - {p['fecha']}"
        enviar_alerta_telegram(msg, img_bytes)
        
        html = f"""
        <html>
        <head>
        <style>
            @media print {{
                @page {{ margin: 0.5cm; }}
                body {{ font-family: Arial, sans-serif; font-size: 9pt; }}
                h2 {{ color: #F57F17; margin-top: 0; font-size: 12pt; margin-bottom: 5px; }}
                .alert-box {{ background-color: #FFF3E0 !important; border-left: 5px solid #F57F17 !important; -webkit-print-color-adjust: exact; padding: 5px !important; margin: 5px 0 !important; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 5px !important; }}
                th {{ background-color: #FFB74D !important; color: white !important; -webkit-print-color-adjust: exact; padding: 2px; }}
                td {{ padding: 2px; border: 1px solid #ddd; }}
                img {{ max-height: 300px !important; width: auto; display: block; margin: 5px auto; }}
                .no-print {{ display: none; }}
            }}
        </style>
        </head>
        <body>
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <table style="width: 100%; border-bottom: 2px solid #F57F17; margin-bottom: 10px;">
                <tr>
                    <td style="width: 80px; padding-bottom: 5px;">
                        <img src="cid:logo_paxban" alt="Logo Paxbán" style="width: 70px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 5px;">
                        <h2 style="color: #F57F17; margin: 0; font-size: 18pt;">⚠️ PRE-ALERTA DE INCENDIO</h2>
                    </td>
                </tr>
            </table>
            <p style="margin: 5px 0;">Estimado usuario,</p>
            <p style="margin: 5px 0;">El sistema ha detectado <strong>{len(pre_alertas)} foco(s) de calor</strong> en la zona de amortiguamiento (10 km) de la concesión.</p>
            <div class="alert-box" style="background-color: #FFF3E0; padding: 10px; border-left: 5px solid #F57F17; margin: 10px 0;">
                <h3 style="margin: 0; color: #E65100; font-size: 14pt;">Zona de Vigilancia</h3>
                <p style="margin: 5px 0 0 0;">Se recomienda monitorear la evolución de estos puntos.</p>
            </div>
            <h4 style="color: #333; margin: 10px 0 5px 0;">Detalles:</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <tr style="background-color: #FFB74D; color: white; text-align: left;">
                    <th style="padding: 5px;">#</th><th style="padding: 5px;">Ubicación</th><th style="padding: 5px;">Coordenadas</th><th style="padding: 5px;">GTM</th><th style="padding: 5px;">Fecha/Hora</th>
                </tr>"""
        for i, p in enumerate(pre_alertas):
            dist_txt = p.get('dist_info', 'Zona de Amortiguamiento')
            html += f"""<tr style="background-color: #ffffff; font-size: 11px;"><td style="padding: 4px; border: 1px solid #ddd;">{i+1}</td><td style="padding: 4px; border: 1px solid #ddd;">{dist_txt}</td><td style="padding: 4px; border: 1px solid #ddd;">{p['lat']:.4f}, {p['lon']:.4f}</td><td style="padding: 4px; border: 1px solid #ddd;">{p['gtm']}</td><td style="padding: 4px; border: 1px solid #ddd;">{p['fecha']}</td></tr>"""
        html += "</table>"
        if img_bytes: html += '<br><img src="cid:mapa_peten" style="max-width: 100%; max-height: 350px; height: auto; border: 1px solid #ddd; border-radius: 5px; display: block; margin: 0 auto;"><br>'
        html += f"""<br><hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;"><div style="font-size: 11px; color: #666;"><p style="margin: 2px 0;"><b>Sistema de Alerta Temprana Paxbán</b><br>Mensaje de advertencia preventiva.<br>Desarrollado por JR23CR</p><p style="text-align: center; margin-top: 10px;" class="no-print"><a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #F57F17; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px;">📂 Ver Galería de Reportes</a></p></div></div></body></html>"""
        enviar_correo_alerta(html, asunto="⚠️ PRE-ALERTA DE INCENDIO - Paxbán", imagen_mapa=img_bytes)

    # 3. REPORTE DIARIO VERDE (Sin amenazas o solo monitoreo)
    elif force_report:
        fecha_hora = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")
        razon = os.environ.get("REPORT_REASON", "automáticamente")
        
        # Mensaje Telegram
        msg = f"🛰️ <b>Reporte de Monitoreo Satelital</b>\n\n" \
              f"✅ <b>Estado: Sin Amenazas Detectadas</b>\n" \
              f"No se han identificado focos activos dentro de las concesiones.\n\n" \
              f"📍 Puntos analizados: {len(puntos)}\n" \
              f"🕒 Hora: {fecha_hora}\n\n" \
              f"Sistema de Alerta Paxbán"
        enviar_alerta_telegram(msg, img_bytes)
        
        # HTML Correo (Tu diseño)
        html = f"""
        <html>
        <head>
        <style>
            @media print {{
                @page {{ margin: 0.5cm; }}
                body {{ font-family: Arial, sans-serif; font-size: 9pt; }}
                h2 {{ color: #2E7D32; margin-top: 0; font-size: 12pt; margin-bottom: 5px; }}
                .status-box {{ background-color: #e8f5e9 !important; border-left: 5px solid #2e7d32 !important; -webkit-print-color-adjust: exact; padding: 5px !important; margin: 5px 0 !important; }}
                img {{ max-height: 320px !important; width: auto; display: block; margin: 5px auto; }}
                p {{ margin: 2px 0; }}
                table {{ margin-bottom: 5px !important; }}
                td {{ padding-bottom: 0 !important; }}
                .no-print {{ display: none; }}
            }}
        </style>
        </head>
        <body>
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <table style="width: 100%; border-bottom: 2px solid #2E7D32; margin-bottom: 10px;">
                <tr>
                    <td style="width: 80px; padding-bottom: 5px;">
                        <img src="cid:logo_paxban" alt="Logo Paxbán" style="width: 70px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 5px;">
                         <h2 style="color: #2E7D32; margin: 0; font-size: 18pt;">Reporte de Monitoreo Satelital</h2>
                    </td>
                </tr>
            </table>
            <p style="margin: 5px 0;">Estimado usuario,</p>
            <p style="margin: 5px 0;">El sistema Alerta Paxbán ha completado el análisis de los datos satelitales más recientes.</p>
            
            <div class="status-box" style="background-color: #e8f5e9; padding: 10px; border-left: 5px solid #2e7d32; margin: 15px 0;">
                <h3 style="margin: 0; color: #1b5e20; font-size: 14pt;">✅ Estado: Sin Amenazas Detectadas</h3>
                <p style="margin: 5px 0 0 0;">No se han identificado focos de incendio activos dentro de los polígonos de las concesiones forestales monitoreadas.</p>
            </div>

            <p style="margin: 5px 0;">
                <b>Puntos analizados en la región:</b> {len(puntos)}<br>
                <b>Hora del reporte:</b> {fecha_hora}
            </p>

            <p style="margin: 5px 0;">A continuación, se presenta el Mapa de Situación Actual en Petén, mostrando la actividad térmica general en la región. Los colores indican la antigüedad del punto de calor (Rojo: &lt;24h, Naranja: &lt;48h, Amarillo: &lt;72h).</p>
        """
        
        if img_bytes: html += '<br><img src="cid:mapa_peten" style="max-width: 100%; max-height: 350px; height: auto; border: 1px solid #ddd; border-radius: 5px; display: block; margin: 0 auto;"><br>'
        
        html += f"""
            <br>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
            <div style="font-size: 11px; color: #666;">
                <p style="margin: 2px 0;">
                    <b>Sistema de Alerta Temprana Paxbán</b><br>
                    Mensaje generado {razon}.<br>
                    Desarrollado por JR23CR
                </p>
                <p style="text-align: center; margin-top: 10px;" class="no-print">
                    <a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #2E7D32; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px;">📂 Ver Galería de Reportes</a>
                </p>
            </div>
        </div>
        </body>
        </html>
        """
        enviar_correo_alerta(html, asunto="Reporte de Monitoreo Satelital", imagen_mapa=img_bytes)

    # Reporte Mensual si se solicita
    if os.environ.get("ACTION_TYPE") == "reporte_mensual":
        generar_reporte_mensual()

    # Generar Galería SIEMPRE (Al final para incluir el reporte mensual si se generó)
    generar_galeria_html()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("❌ ERROR FATAL EN EL SCRIPT:", file=sys.stderr)
        traceback.print_exc()
        # No salimos con error para permitir que GitHub Pages intente desplegar lo que haya
        sys.exit(0) 
