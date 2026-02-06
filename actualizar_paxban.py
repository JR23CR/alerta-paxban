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

# Configuración oficial GTM (Guatemala Transversal Mercator)
GTM_PROJ_STR = "+proj=tmerc +lat_0=0 +lon_0=-90.5 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"

def convertir_a_gtm(lon, lat):
    """Convierte coordenadas de WGS84 (lat, lon) a GTM."""
    if not Transformer:
        return "No disponible"
    try:
        transformer = Transformer.from_crs(
            "EPSG:4326", 
            GTM_PROJ_STR,
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
        trans_to_meter = Transformer.from_crs("EPSG:4326", GTM_PROJ_STR, always_xy=True)
        
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

def calcular_campamento_cercano(lon, lat):
    """Calcula el campamento más cercano y la distancia."""
    if not Transformer: return "N/A"
    try:
        trans_to_gtm = Transformer.from_crs("EPSG:4326", GTM_PROJ_STR, always_xy=True)
        fx, fy = trans_to_gtm.transform(lon, lat)
        min_dist = float('inf')
        nearest_camp = None
        nearest_coords = None
        for c in CAMPAMENTOS:
            # Distancia Euclidiana
            dist = math.sqrt((fx - c['x'])**2 + (fy - c['y'])**2)
            if dist < min_dist:
                min_dist = dist
                nearest_camp = c['nombre']
                nearest_coords = (c['x'], c['y'])
        if nearest_camp:
            cx, cy = nearest_coords
            angle = math.degrees(math.atan2(fy - cy, fx - cx))
            if angle < 0: angle += 360
            
            if 337.5 <= angle or angle < 22.5: card = "al Este"
            elif 22.5 <= angle < 67.5: card = "al Noreste"
            elif 67.5 <= angle < 112.5: card = "al Norte"
            elif 112.5 <= angle < 157.5: card = "al Noroeste"
            elif 157.5 <= angle < 202.5: card = "al Oeste"
            elif 202.5 <= angle < 247.5: card = "al Suroeste"
            elif 247.5 <= angle < 292.5: card = "al Sur"
            else: card = "al Sureste"
            
            return f"{int(min_dist)}m de {nearest_camp} {card}"
    except Exception:
        pass
    return "N/A"

def enviar_correo_alerta(cuerpo_html, asunto="🔥 Alerta Paxban", imagen_mapa=None, archivo_zip=None):
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
    """Guarda el mapa en la carpeta mapa_reporte_diario."""
    if not imagen_bytes: return
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    mes_nombre = MESES_ES.get(fecha_dt.strftime("%m"), fecha_dt.strftime("%m"))
    carpeta = os.path.join("mapa_reporte_diario", fecha_dt.strftime("%Y"), mes_nombre)
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
        # Escanear tanto la carpeta estándar como la carpeta '2.4' detectada
        for base_dir in ["mapa_reporte_diario", "2.4"]:
            if os.path.exists(base_dir):
                for root, _, files in os.walk(base_dir):
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
                                nombre_mostrar = f"{mes_num} {anio}"
                        except: pass
                        
                        reportes_mensuales.append({"url": url, "nombre": nombre_mostrar, "filename": file})
        
        print(f"📦 Se encontraron {len(reportes_mensuales)} reportes mensuales.")
        # Ordenar por nombre de archivo original para mantener orden cronológico
        reportes_mensuales.sort(key=lambda x: x['filename'], reverse=True)

        html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reportes Paxban</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .card-img-top { height: 200px; object-fit: cover; }
            @media (max-width: 768px) { 
                h1 { font-size: 1.5rem; } 
                .container { padding-left: 15px; padding-right: 15px; }
                /* En móvil el botón es sólido para que no se vea como un bloque blanco vacío */
                .btn-pc-outline { background-color: #198754 !important; color: white !important; width: 100%; }
            }
            @media (min-width: 769px) {
                .btn-pc-outline { width: auto; }
            }
        </style>
        </head><body class="bg-light">
        <div class="container py-4 py-md-5">
            <div class="d-flex flex-column flex-md-row justify-content-between align-items-center mb-4 gap-3">
                <h1 class="text-success fw-bold m-0">📂 Galería de Reportes</h1>
                <a href="index.html" class="btn btn-outline-success btn-pc-outline px-4 shadow-sm">🏠 Volver al Inicio</a>
            </div>"""
        
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

def generar_mapa_imagen(puntos, concesiones=None, center_point=None, buffer=0.1):
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

        paxban_poly = None
        if concesiones:
            for nombre, poly in concesiones.items():
                if "Paxbán" in nombre:
                    paxban_poly = poly
                    break

        if center_point:
            lon, lat = center_point
            minx, miny = transformer.transform(lon - buffer, lat - buffer)
            maxx, maxy = transformer.transform(lon + buffer, lat + buffer)
        else:
            # Enfocar en la región de Petén (Vista general amplia anterior)
            minx, miny = transformer.transform(-91.5, 15.8)
            maxx, maxy = transformer.transform(-89.0, 17.9)

        ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy)
        
        try:
            cx.add_basemap(ax, crs="EPSG:3857", source=cx.providers.Esri.NatGeoWorldMap, attribution=False)
        except Exception as e:
            print(f"⚠️ Advertencia: No se pudo descargar el mapa base ({e}). Se generará sin fondo.", file=sys.stderr)
            
        ax.set_axis_off()
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
        buf.seek(0); plt.close(fig)
        return buf.read()
    except Exception as e:
        print(f"⚠️ Error generando mapa: {e}", file=sys.stderr)
        return None

def crear_informe_word(ruta_salida, mes_nombre, anio, fires_list, map_images, concesiones=None):
    if not Document: return
    try:
        doc = Document()
        
        # Configuración de estilo base (Arial 11)
        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(11)

        # Título Principal
        title = doc.add_heading('SISTEMA DE ALERTA TEMPRANA PAXBAN', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Mes del Informe
        subtitle = doc.add_heading(f'INFORME MENSUAL: {mes_nombre.upper()} {anio}', 1)
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Introducción Técnica
        intro_text = (
            "El presente documento constituye el informe técnico mensual generado por el Sistema de Alerta Temprana Paxbán, "
            "una herramienta tecnológica de vanguardia implementada para la vigilancia permanente y detección oportuna de "
            "anomalías térmicas en la Concesión Industrial Paxbán, ubicada en la Zona de Uso Múltiple de la Reserva de la "
            "Biosfera Maya (RBM). Este software opera de manera automatizada en la nube, integrando datos satelitales de "
            "alta resolución en tiempo real con análisis geoespacial preciso, con el objetivo primordial de fortalecer las "
            "capacidades de respuesta rápida y proporcionar información crítica para la gestión forestal sostenible y la "
            "protección de la biodiversidad, en cumplimiento con los lineamientos del Consejo Nacional de Áreas Protegidas (CONAP)."
        )
        p_intro = doc.add_paragraph(intro_text)
        p_intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Sección de Metodología
        doc.add_heading('Metodología de Monitoreo', 2)
        metodo_text = (
            "La metodología empleada se basa en el monitoreo constante de los sensores MODIS (Moderate Resolution Imaging "
            "Spectroradiometer) y VIIRS (Visible Infrared Imaging Radiometer Suite) a través de la plataforma NASA FIRMS. "
            "El sistema realiza un filtrado geoespacial automatizado para identificar focos de calor dentro de los límites "
            "oficiales de la concesión y en su zona de amortiguamiento perimetral, permitiendo una clasificación de alertas "
            "por nivel de riesgo y proximidad a campamentos de control."
        )
        p_metodo = doc.add_paragraph(metodo_text)
        p_metodo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Sección de Objetivos
        doc.add_heading('Objetivos del Sistema', 2)
        objs = doc.add_paragraph("• Detectar de forma temprana focos de incendio forestal para minimizar el impacto ambiental.\n"
                                 "• Proveer coordenadas precisas en formato GTM para facilitar el despliegue de cuadrillas terrestres.\n"
                                 "• Mantener un registro histórico auditable de la actividad térmica en la región.")
        objs.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Resumen de Detecciones
        doc.add_heading('Resultados del Periodo', 2)
        if fires_list:
            resumen_p = doc.add_paragraph(f"Durante el mes de {mes_nombre} de {anio}, se identificaron {len(fires_list)} puntos de calor dentro del área de interés:")
            resumen_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            
            for i, fire in enumerate(fires_list, 1):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                ref = fire.get('dist_campamento', 'N/A')
                gtm = fire.get('gtm', 'N/A')
                fecha = fire.get('fecha', 'N/A')
                p.add_run(f"Punto de detección térmica No. {i}: ").bold = True
                p.add_run(f"Identificado el {fecha}. Referencia de ubicación: {ref}. Coordenadas proyectadas GTM: {gtm}.")
                
                # Generar e insertar imagen enfocada para este punto
                if concesiones:
                    img_focused = generar_mapa_imagen([fire], concesiones, center_point=(fire['lon'], fire['lat']), buffer=0.08)
                    if img_focused:
                        img_stream = BytesIO(img_focused)
                        doc.add_picture(img_stream, width=Inches(4.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                doc.add_paragraph("") # Espacio entre puntos
        else:
            resumen_p = doc.add_paragraph(
                f"Durante el periodo correspondiente al mes de {mes_nombre}, el sistema mantuvo un monitoreo ininterrumpido de 24 horas diarias. "
                f"Tras el análisis de los datos satelitales procesados, se informa que no se detectaron anomalías térmicas ni alertas de incendio dentro de los límites de la Concesión Industrial Paxbán."
            )
            resumen_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Inserción de Mapas (Máximo 4)
        if map_images:
            doc.add_page_break()
            doc.add_heading('Mapas de Situación Mensual', 2).alignment = WD_ALIGN_PARAGRAPH.CENTER
            for img_path in map_images[:4]:
                if os.path.exists(img_path):
                    doc.add_picture(img_path, width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Firma Final
        doc.add_paragraph("\n\n")
        firma = doc.add_paragraph("Sistema de Alerta Temprana Paxban")
        firma.alignment = WD_ALIGN_PARAGRAPH.CENTER
        firma_run = firma.add_run("\ndesarrollado por\nNery Jose Corado Ramírez\nMiembro de la CIF\nGIBOR, S.A")
        firma_run.italic = True

        doc.save(ruta_salida)
    except Exception as e:
        print(f"⚠️ Error creando Word: {e}", file=sys.stderr)

def generar_reporte_mensual(concesiones):
    """Genera ZIP mensual."""
    print("📦 Iniciando generación de Reporte Mensual...")
    try:
        fecha_dt = datetime.utcnow() - timedelta(hours=6)
        # Permitir especificar mes y año vía variables de entorno para reportes retroactivos
        anio = os.environ.get("TARGET_YEAR") or fecha_dt.strftime("%Y")
        mes = os.environ.get("TARGET_MONTH") or fecha_dt.strftime("%m")
        nombre_mes = MESES_ES.get(mes, mes)
        
        raiz = f"Reporte_{mes}_{anio}"
        if os.path.exists(raiz): shutil.rmtree(raiz)
        os.makedirs(raiz)
        
        # Copiar carpetas
        for d in ["Reporte Diario", "Incendios Detectados", "Informe de Puntos de Calor"]:
            os.makedirs(os.path.join(raiz, d), exist_ok=True)
            
        # Copiar contenido de mapa_reporte_diario y también de '2.4' si existen para el mes
        fuentes = [
            os.path.join("mapa_reporte_diario", anio, nombre_mes),
            os.path.join("2.4", anio, mes) # Formato numérico
        ]
        
        for src in fuentes:
            if os.path.exists(src):
                print(f"📂 Copiando mapas desde: {src}")
                for f in os.listdir(src):
                    if f.endswith(".png"):
                        shutil.copy2(os.path.join(src, f), os.path.join(raiz, "Reporte Diario"))

        # Recolectar detalles de incendios y copiar imágenes
        fires_details = []
        src_alertas = os.path.join("bitacora", anio, mes, "alertas")
        if os.path.exists(src_alertas):
            for f in sorted(os.listdir(src_alertas)):
                if f.endswith(".png"):
                    shutil.copy2(os.path.join(src_alertas, f), os.path.join(raiz, "Incendios Detectados"))
                elif f.endswith(".json"):
                    try:
                        with open(os.path.join(src_alertas, f), 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                            if isinstance(data, list): fires_details.extend(data)
                            else: fires_details.append(data)
                    except: pass

        # Recolectar los últimos 4 mapas diarios para el Word
        map_images_paths = []
        for src in fuentes:
            if os.path.exists(src):
                maps = [os.path.join(src, f) for f in os.listdir(src) if f.endswith(".png")]
                map_images_paths.extend(maps)
        
        map_images_paths.sort(reverse=True)
        map_images_paths = map_images_paths[:4]

        # Generar Word con el nuevo formato
        crear_informe_word(
            os.path.join(raiz, "Informe de Puntos de Calor", "Informe.docx"), 
            nombre_mes, anio, fires_details, map_images_paths,
            concesiones=concesiones
        )

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
                        <img src="cid:logo_paxban" alt="Logo Paxban" style="width: 90px; height: auto;">
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
                <p><b>Sistema de Alerta Temprana Paxban</b><br>Mensaje generado automáticamente.<br>Desarrollado por JR23CR</p>
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
    print("🚀 Iniciando sistema Paxban...")
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
                "concesion": "Paxbán", "gtm": convertir_a_gtm(-90.15, 17.7),
                "dist_info": None,
                "dist_campamento": calcular_campamento_cercano(-90.15, 17.7)
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
                "dist_info": dist_info_test,
                "dist_campamento": "N/A"
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
                            dist_campamento_str = "N/A"
                            dist_info = None
                            
                            for nom, poly in concesiones.items():
                                if "Paxbán" in nom:
                                    if poly.contains(p):
                                        en_paxban = True
                                        concesion_nombre = "Paxbán"
                                        dist_campamento_str = calcular_campamento_cercano(lon, lat)
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
                                "dist_info": dist_info,
                                "dist_campamento": dist_campamento_str
                            })
                        except: pass
            except Exception as e:
                print(f"⚠️ Error descargando {sat}: {e}", file=sys.stderr)

        if not puntos:
            print("⚠️ Advertencia: No se encontraron datos de incendios en el área seleccionada.")

    # Guardar JSON para la web
    with open('incendios.json', 'w') as f: json.dump(puntos, f)
    
    # Solo alertar sobre puntos detectados en las últimas 1.5 horas para evitar duplicados en ejecuciones horarias
    alertas = [p for p in puntos if p['alerta'] and p['horas'] <= 1.5]
    pre_alertas = [p for p in puntos if p.get('pre_alerta') and p['horas'] <= 1.5]
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
        msg = f"🔥 <b>ALERTA PAXBAN</b>\n"
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
                        <img src="cid:logo_paxban" alt="Logo Paxban" style="width: 70px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 5px;">
                        <h2 style="color: #D32F2F; margin: 0; font-size: 18pt;">🔥 ALERTA DE INCENDIO DETECTADO 🔥</h2>
                    </td>
                </tr>
            </table>
            <p style="margin: 5px 0;">Estimado usuario,</p>
            <p style="margin: 5px 0;"><strong>¡Atención!</strong> El sistema Alerta Paxban4 ha identificado <strong>{len(alertas)} foco(s) de incendio activos</strong> dentro de los polígonos de las concesiones monitoreadas.</p>
            <div class="alert-box" style="background-color: #ffcdd2; padding: 10px; border-left: 5px solid #D32F2F; margin: 10px 0;">
                <h3 style="margin: 0; color: #b71c1c; font-size: 14pt;">Resumen de la Alerta</h3>
                <p style="margin: 5px 0 0 0;">Se requiere verificación y acción inmediata.</p>
            </div>
            <h4 style="color: #333; margin: 10px 0 5px 0;">Detalles de los Focos Detectados:</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <tr style="background-color: #ef5350; color: white; text-align: left;">
                    <th style="padding: 5px; border: 1px solid #ddd;">#</th><th style="padding: 5px; border: 1px solid #ddd;">Referencia</th><th style="padding: 5px; border: 1px solid #ddd;">Coordenadas</th><th style="padding: 5px; border: 1px solid #ddd;">GTM</th><th style="padding: 5px; border: 1px solid #ddd;">Fecha/Hora</th>
                </tr>"""
        for i, p in enumerate(alertas):
            html += f"""
            <tr style="background-color: {'#ffebee' if i % 2 == 0 else '#ffffff'}; font-size: 11px;">
                <td style="padding: 4px; border: 1px solid #ddd;">{i+1}</td>
                <td style="padding: 4px; border: 1px solid #ddd;"><strong>{p.get('dist_campamento', 'N/A')}</strong></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['lat']:.4f}, {p['lon']:.4f}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['gtm']}</td>
                <td style="padding: 4px; border: 1px solid #ddd;">{p['fecha']}</td>
            </tr>"""
        html += "</table>"
        html += '<p style="margin: 10px 0 5px 0;">A continuación se presenta el mapa de la situación:</p>'
        if img_bytes: html += '<br><img src="cid:mapa_peten" style="max-width: 100%; max-height: 350px; height: auto; border: 1px solid #ddd; border-radius: 5px; display: block; margin: 0 auto;"><br>'
        html += f"""<br><hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;"><div style="font-size: 11px; color: #666;"><p style="margin: 2px 0;"><b>Sistema de Alerta Temprana Paxban</b><br>Mensaje generado por detección de amenaza.<br>Desarrollado por JR23CR</p><p style="text-align: center; margin-top: 10px;" class="no-print"><a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #D32F2F; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px;">📂 Ver Galería de Reportes</a></p></div></div></body></html>"""
        enviar_correo_alerta(html, asunto="🔥 ALERTA DE INCENDIO - Paxban", imagen_mapa=img_bytes)
        
    # 2. PRE-ALERTA AMARILLA (Incendio CERCA de Paxbán)
    elif pre_alertas:
        print(f"📧 Enviando Pre-Alerta por {len(pre_alertas)} focos...")
        msg = f"⚠️ <b>PRE-ALERTA PAXBAN</b>\n"
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
                        <img src="cid:logo_paxban" alt="Logo Paxban" style="width: 70px; height: auto;">
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
        html += f"""<br><hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;"><div style="font-size: 11px; color: #666;"><p style="margin: 2px 0;"><b>Sistema de Alerta Temprana Paxban</b><br>Mensaje de advertencia preventiva.<br>Desarrollado por JR23CR</p><p style="text-align: center; margin-top: 10px;" class="no-print"><a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #F57F17; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px;">📂 Ver Galería de Reportes</a></p></div></div></body></html>"""
        enviar_correo_alerta(html, asunto="⚠️ PRE-ALERTA DE INCENDIO - Paxban", imagen_mapa=img_bytes)

    # 3. REPORTE DIARIO VERDE (Sin amenazas o solo monitoreo)
    elif force_report:
        fecha_hora = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")
        razon = os.environ.get("REPORT_REASON", "automáticamente")
        
        # Solo enviar notificaciones si NO es el reporte automático programado de las 4 PM
        # (Se mantiene el guardado del mapa en la galería pero sin el correo verde)
        es_reporte_programado = "automáticamente" in razon and "Reporte Diario" in razon
        
        if not es_reporte_programado:
            # Mensaje Telegram
            msg = f"🛰️ <b>Reporte de Monitoreo Satelital</b>\n\n" \
                  f"✅ <b>Estado: Sin Amenazas Detectadas</b>\n" \
                  f"No se han identificado focos activos dentro de las concesiones.\n\n" \
                  f"📍 Puntos analizados: {len(puntos)}\n" \
                  f"🕒 Hora: {fecha_hora}\n\n" \
                  f"Sistema de Alerta Temprana Paxban"
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
                        <img src="cid:logo_paxban" alt="Logo Paxban" style="width: 70px; height: auto;">
                    </td>
                    <td style="vertical-align: middle; padding-bottom: 5px;">
                         <h2 style="color: #2E7D32; margin: 0; font-size: 18pt;">Reporte de Monitoreo Satelital</h2>
                    </td>
                </tr>
            </table>
            <p style="margin: 5px 0;">Estimado usuario,</p>
            <p style="margin: 5px 0;">El sistema Alerta Paxban ha completado el análisis de los datos satelitales más recientes.</p>
            
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
                    <b>Sistema de Alerta Temprana Paxban</b><br>
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
        if not es_reporte_programado:
            enviar_correo_alerta(html, asunto="Reporte de Monitoreo Satelital", imagen_mapa=img_bytes)
        else:
            print("ℹ️ Reporte diario procesado (Mapa guardado), pero se omite el envío de correo por ser programado.")

    # Reporte Mensual si se solicita
    if os.environ.get("ACTION_TYPE") == "reporte_mensual":
        generar_reporte_mensual(concesiones)

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
