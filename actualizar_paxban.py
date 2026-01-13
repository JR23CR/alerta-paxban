import os
import sys
import json
import smtplib
import shutil
from datetime import datetime, timedelta
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

import requests
from shapely.geometry import shape, Point
from shapely.ops import transform

# Configurar matplotlib para que funcione sin pantalla (servidor) antes de importar pyplot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt # noqa: E402
import contextily as cx # noqa: E402
from matplotlib.lines import Line2D # noqa: E402

try:
    from pyproj import Transformer # noqa: E402
except ImportError:
    Transformer = None
    print("Advertencia: pyproj no está instalado. Las coordenadas GTM no se calcularán.", file=sys.stderr)

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

def convertir_a_gtm(lon, lat):
    """Convierte coordenadas de WGS84 (lat, lon) a GTM."""
    if not Transformer:
        return "No disponible"
    try:
        # Define la transformación de WGS84 (EPSG:4326) a GTM
        # El código EPSG para GTM no es estándar, usamos su definición Proj4
        # Esta es una definición común para GTM.
        transformer = Transformer.from_crs(
            "EPSG:4326", 
            "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs",
            always_xy=True # Asegura que el orden de entrada es (lon, lat)
        )
        gtm_x, gtm_y = transformer.transform(lon, lat)
        return f"{gtm_x:.2f} E, {gtm_y:.2f} N"
    except Exception as e:
        print(f"Error convirtiendo coordenadas: {e}", file=sys.stderr)
        return "No disponible"

def enviar_correo_alerta(cuerpo_html, asunto="🔥 Alerta Temprana de Incendio en Concesión Forestal", imagen_mapa=None, archivo_zip=None):
    """Envía un correo electrónico de alerta usando credenciales de entorno."""
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = os.environ.get("SMTP_PORT")
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL]):
        print("Advertencia: Faltan una o más variables de entorno para el envío de correo. No se enviará la alerta.", file=sys.stderr)
        return

    # Procesar lista de destinatarios (separados por comas)
    destinatarios = [email.strip() for email in RECIPIENT_EMAIL.split(',') if email.strip()]

    # Agregar fecha y hora al asunto para diferenciar correos
    # Hora de Guatemala (UTC-6)
    fecha_hora = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")
    asunto_completo = f"{asunto} - {fecha_hora}"

    print(f"Enviando correo de alerta a {len(destinatarios)} destinatarios...")
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = asunto_completo
        
        msg.attach(MIMEText(cuerpo_html, 'html', 'utf-8'))
        
        # Adjuntar imagen del mapa si existe
        if imagen_mapa:
            img = MIMEImage(imagen_mapa)
            img.add_header('Content-ID', '<mapa_peten>')
            img.add_header('Content-Disposition', 'inline', filename='mapa_peten.png')
            msg.attach(img)
            
        # Adjuntar archivo ZIP si existe (Reporte Mensual)
        if archivo_zip:
            nombre_archivo, datos_archivo = archivo_zip
            part = MIMEApplication(datos_archivo, Name=nombre_archivo)
            part['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("✅ Correo de alerta enviado exitosamente.")
    except Exception as e:
        print(f"Error crítico: No se pudo enviar el correo de alerta. Causa: {e}", file=sys.stderr)

def enviar_alerta_telegram(mensaje, imagen_bytes=None):
    """Envía un mensaje de texto a uno o varios chats de Telegram usando un Bot."""
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_ID")

    if not all([BOT_TOKEN, CHAT_IDS_RAW]):
        print("Advertencia: Faltan variables de entorno para Telegram. No se enviará el mensaje.", file=sys.stderr)
        return
    
    # Permitir múltiples destinatarios separados por coma
    chat_ids = [cid.strip() for cid in CHAT_IDS_RAW.split(',') if cid.strip()]

    for chat_id in chat_ids:
        if imagen_bytes:
            # Enviar foto con texto (caption)
            api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            files = {'photo': ('mapa.png', imagen_bytes, 'image/png')}
            data = {
                'chat_id': chat_id,
                'caption': mensaje,
                'parse_mode': 'HTML'
            }
        else:
            # Enviar solo texto
            api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': mensaje,
                'parse_mode': 'HTML'
            }
            files = None

        try:
            print(f"Enviando notificación a Telegram ID {chat_id}...")
            if files:
                response = requests.post(api_url, data=data, files=files, timeout=20)
            else:
                response = requests.post(api_url, json=data, timeout=10)
                
            response.raise_for_status()
            if not response.json().get('ok'):
                print(f"Error en la respuesta de la API de Telegram: {response.text}", file=sys.stderr)
            else:
                print(f"✅ Mensaje de Telegram enviado exitosamente a {chat_id}.")
        except requests.exceptions.RequestException as e:
            print(f"Error crítico: No se pudo enviar el mensaje de Telegram a {chat_id}. Causa: {e}", file=sys.stderr)

def guardar_mapa_local(imagen_bytes):
    """Guarda la imagen en la estructura de carpetas 2.4/Año/Mes para CONAP."""
    if not imagen_bytes:
        return

    # Obtener fecha actual (UTC-6 para Guatemala)
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    anio = fecha_dt.strftime("%Y")
    mes = fecha_dt.strftime("%m")
    fecha_str = fecha_dt.strftime("%Y-%m-%d")
    
    # Crear estructura de directorios: 2.4/2026/01/
    carpeta = os.path.join("2.4", anio, mes)
    os.makedirs(carpeta, exist_ok=True)
    
    nombre_archivo = f"Mapa_Calor_{fecha_str}.png"
    ruta_completa = os.path.join(carpeta, nombre_archivo)
    
    with open(ruta_completa, "wb") as f:
        f.write(imagen_bytes)
    print(f"✅ Mapa guardado para CONAP en: {ruta_completa}")

def guardar_bitacora(imagen_bytes, tipo, datos_puntos):
    """Guarda evidencia de alertas/pre-alertas en la carpeta bitacora para el reporte mensual."""
    if not imagen_bytes: return
    
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    anio = fecha_dt.strftime("%Y")
    mes = fecha_dt.strftime("%m")
    fecha_str = fecha_dt.strftime("%Y-%m-%d_%H%M")
    
    # Tipo: 'alertas' (Incendios Paxban) o 'pre_alertas' (Puntos de Calor/Cerca)
    carpeta = os.path.join("bitacora", anio, mes, tipo)
    os.makedirs(carpeta, exist_ok=True)
    
    nombre_img = f"{tipo}_{fecha_str}.png"
    ruta_img = os.path.join(carpeta, nombre_img)
    
    with open(ruta_img, "wb") as f:
        f.write(imagen_bytes)
        
    # Guardar JSON con detalles para referencia
    nombre_json = f"{tipo}_{fecha_str}.json"
    ruta_json = os.path.join(carpeta, nombre_json)
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(datos_puntos, f, indent=2, ensure_ascii=False)

def generar_galeria_html():
    """Genera una página HTML (reportes.html) que lista todos los mapas históricos."""
    ruta_base = "2.4"
    if not os.path.exists(ruta_base):
        return

    mapas = []
    for root, dirs, files in os.walk(ruta_base):
        for file in files:
            if file.endswith(".png"):
                ruta_completa = os.path.join(root, file)
                # Convertir ruta a URL relativa
                url = ruta_completa.replace(os.sep, '/')
                mapas.append({
                    "url": url,
                    "nombre": file,
                    "fecha": file.replace("Mapa_Calor_", "").replace(".png", "")
                })
    
    # Ordenar por fecha descendente (lo más nuevo arriba)
    mapas.sort(key=lambda x: x['fecha'], reverse=True)

    html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reportes Paxbán - CONAP</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light">
    <div class="container py-5">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1 class="text-success m-0">📂 Histórico de Reportes (Carpeta 2.4)</h1>
            <a href="./" class="btn btn-outline-success">🏠 Volver al Inicio</a>
        </div>
        <div class="row row-cols-1 row-cols-md-3 g-4">"""
    
    for m in mapas:
        html += f"""
        <div class="col"><div class="card h-100 shadow-sm">
            <img src="{m['url']}" class="card-img-top" alt="{m['nombre']}" loading="lazy" style="height: 250px; object-fit: cover;">
            <div class="card-body"><h5 class="card-title">{m['fecha']}</h5><p class="card-text text-muted small">{m['nombre']}</p>
            <a href="{m['url']}" class="btn btn-primary btn-sm" download target="_blank" style="text-decoration: none;">⬇️ Descargar</a> <a href="{m['url']}" class="btn btn-outline-secondary btn-sm" target="_blank" style="text-decoration: none;">🔍 Ver</a>
        </div></div></div>"""

    html += """</div></div></body></html>"""
    
    with open("reportes.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ Galería Web generada: reportes.html")

def generar_mapa_imagen(puntos, concesiones=None):
    """Genera una imagen PNG del mapa de Petén con los puntos de calor."""
    print("Generando imagen del mapa...")
    
    if not Transformer:
        print("Error: pyproj no está instalado, no se puede generar el mapa.", file=sys.stderr)
        return None

    try:
        # Convertir puntos a Web Mercator (EPSG:3857) para el mapa base
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        xs, ys, colores = [], [], []
        
        for p in puntos:
            x, y = transformer.transform(p['lon'], p['lat'])
            xs.append(x)
            ys.append(y)
            colores.append(p['color'])
        
        # Crear figura
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Dibujar polígonos de concesiones si existen
        if concesiones:
            for nombre, poligono in concesiones.items():
                # Filtrar para mostrar solo el polígono de Paxbán
                if "Paxbán" not in nombre:
                    continue

                try:
                    # Transformar polígono a Web Mercator (3857) para coincidir con el mapa base
                    poligono_3857 = transform(transformer.transform, poligono)
                    
                    # Función auxiliar para dibujar
                    def plot_poly(geom):
                        x, y = geom.exterior.xy
                        ax.plot(x, y, color='#2e7d32', linewidth=2, alpha=0.8, zorder=1) # Verde bosque

                    if poligono_3857.geom_type == 'Polygon':
                        plot_poly(poligono_3857)
                    elif poligono_3857.geom_type == 'MultiPolygon':
                        for poly in poligono_3857.geoms:
                            plot_poly(poly)
                except Exception as e:
                    print(f"Error dibujando concesión {nombre}: {e}", file=sys.stderr)

        # Si hay puntos, graficarlos
        if xs:
            ax.scatter(xs, ys, c=colores, s=50, alpha=0.8, edgecolors='white', linewidth=1, zorder=2)
        
        # Agregar Leyenda para CONAP (24h, 48h, 72h)
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', label='< 24 horas', markerfacecolor='red', markersize=10),
            Line2D([0], [0], marker='o', color='w', label='24 - 48 horas', markerfacecolor='orange', markersize=10),
            Line2D([0], [0], marker='o', color='w', label='48 - 72 horas', markerfacecolor='yellow', markersize=10)
        ]
        ax.legend(handles=legend_elements, loc='upper right', title="Puntos de Calor")

        # Definir límites del mapa (Petén aproximado) si no hay suficientes puntos para auto-escala
        # O para asegurar que siempre se vea Petén
        minx, miny = transformer.transform(-91.5, 15.8) # Suroeste
        maxx, maxy = transformer.transform(-89.0, 17.9) # Noreste
        
        # Ajustar vista para incluir puntos si están fuera, o mantener vista de Petén
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        
        # Agregar mapa base de National Geographic
        cx.add_basemap(ax, crs="EPSG:3857", source=cx.providers.Esri.NatGeoWorldMap, attribution=False)
        ax.set_axis_off()
        
        # Guardar en memoria
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
        buf.seek(0)
        plt.close(fig)
        return buf.read()
    except Exception as e:
        print(f"Error generando el mapa: {e}", file=sys.stderr)
        return None

def generar_reporte_mensual():
    """Genera el ZIP mensual con la estructura solicitada y envía correo."""
    fecha_dt = datetime.utcnow() - timedelta(hours=6)
    anio = fecha_dt.strftime("%Y")
    mes = fecha_dt.strftime("%m")
    
    nombres_meses = {"01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril", "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto", "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"}
    nombre_mes_es = nombres_meses.get(mes, "Mes_Actual")
    
    print(f"📦 Generando Reporte Mensual Estructurado: {nombre_mes_es} {anio}")
    
    # Nombre de la carpeta raíz del reporte
    nombre_carpeta_raiz = f"{nombre_mes_es}" # Ejemplo: "Enero"
    if os.path.exists(nombre_carpeta_raiz): shutil.rmtree(nombre_carpeta_raiz)
    os.makedirs(nombre_carpeta_raiz)
    
    # 1. Carpeta: Reporte Diario (Todas las fotos de Petén y puntos de calor)
    dir_diario = os.path.join(nombre_carpeta_raiz, "Reporte Diario")
    os.makedirs(dir_diario, exist_ok=True)
    origen_diario = os.path.join("2.4", anio, mes)
    if os.path.exists(origen_diario):
        for f in os.listdir(origen_diario):
            shutil.copy2(os.path.join(origen_diario, f), dir_diario)
            
    # 2. Carpeta: Incendios Detectados (Solo incendios DENTRO de Paxbán)
    dir_incendios = os.path.join(nombre_carpeta_raiz, "Incendios Detectados")
    os.makedirs(dir_incendios, exist_ok=True)
    origen_alertas = os.path.join("bitacora", anio, mes, "alertas")
    if os.path.exists(origen_alertas):
        for f in os.listdir(origen_alertas):
            if f.endswith(".png"):
                shutil.copy2(os.path.join(origen_alertas, f), dir_incendios)

    # 3. Carpeta: Informe de Puntos de Calor (Resumen + Imágenes cerca de Paxbán)
    dir_informe = os.path.join(nombre_carpeta_raiz, "Informe de Puntos de Calor")
    os.makedirs(dir_informe, exist_ok=True)
    
    # Copiar imagenes de pre-alertas (cerca de Paxban)
    origen_pre = os.path.join("bitacora", anio, mes, "pre_alertas")
    if os.path.exists(origen_pre):
        for f in os.listdir(origen_pre):
            if f.endswith(".png"):
                shutil.copy2(os.path.join(origen_pre, f), dir_informe)
                
    # Generar Resumen de Texto
    resumen_txt = f"INFORME MENSUAL DE PUNTOS DE CALOR - {nombre_mes_es.upper()} {anio}\n\n"
    resumen_txt += f"Concesión: Paxbán\nFecha de generación: {fecha_dt.strftime('%d/%m/%Y')}\n\n"
    resumen_txt += "ESTADO DEL MES:\n"
    
    hay_incendios = len(os.listdir(dir_incendios)) > 0 if os.path.exists(dir_incendios) else False
    hay_puntos_cerca = len(os.listdir(dir_informe)) > 0 if os.path.exists(dir_informe) else False
    
    if hay_incendios:
        resumen_txt += "- SE DETECTARON incendios activos dentro de la concesión (Ver carpeta 'Incendios Detectados').\n"
    else:
        resumen_txt += "- NO se detectaron incendios activos dentro del polígono de Paxbán.\n"
        
    if hay_puntos_cerca:
        resumen_txt += "- Se registraron puntos de calor en áreas aledañas (Ver imágenes en esta carpeta).\n"
    
    with open(os.path.join(dir_informe, "Resumen_Estado.txt"), "w") as f:
        f.write(resumen_txt)

    # Crear ZIP
    zip_name = f"Reporte_Mensual_{nombre_mes_es}_{anio}"
    shutil.make_archive(zip_name, 'zip', root_dir='.', base_dir=nombre_carpeta_raiz)
    
    # Mover ZIP a carpeta pública
    os.makedirs("descargas", exist_ok=True)
    ruta_final_zip = os.path.join("descargas", f"{zip_name}.zip")
    shutil.move(f"{zip_name}.zip", ruta_final_zip)
    shutil.rmtree(nombre_carpeta_raiz) # Limpiar carpeta temporal
    
    print(f"✅ ZIP generado exitosamente: {ruta_final_zip}")
    
    # Leer el archivo ZIP para adjuntarlo
    with open(ruta_final_zip, "rb") as f:
        zip_bytes = f.read()
    
    # Enviar Correo
    link_descarga = f"https://JR23CR.github.io/alerta-paxban/descargas/{zip_name}.zip"
    cuerpo = f"<html><body><h2>📂 Reporte Mensual: {nombre_mes_es} {anio}</h2><p>Adjunto encontrará el archivo comprimido con las carpetas solicitadas (Reporte Diario, Incendios Detectados, Informe Puntos de Calor).</p><p>También puede descargarlo desde el siguiente enlace si el adjunto falla:</p><p><a href='{link_descarga}' style='background:#2e7d32;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;'>⬇️ Descargar Carpeta Mensual (.zip)</a></p></body></html>"
    enviar_correo_alerta(cuerpo, asunto=f"Reporte Mensual {nombre_mes_es} {anio}", archivo_zip=(f"{zip_name}.zip", zip_bytes))

def cargar_concesiones(archivo_geojson):
    """Carga todas las áreas del GeoJSON en un diccionario de objetos Shapely."""
    concesiones = {}
    with open(archivo_geojson, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for feature in data['features']:
            nombre = feature['properties'].get('Name', 'Área desconocida')
            concesiones[nombre] = shape(feature['geometry'])
    return concesiones

def obtener_incendios():
    # Verificar si es solicitud de reporte mensual
    action_type = os.environ.get("ACTION_TYPE", "monitor")
    if action_type == "reporte_mensual":
        generar_reporte_mensual()
        return

    dict_concesiones = cargar_concesiones('concesiones1.geojson')
    print(f"Cargadas {len(dict_concesiones)} concesiones para monitoreo.")

    # 1. Calcular Zona de Pre-Alerta (Buffer de 10km alrededor de Paxbán)
    zona_pre_alerta = None
    poly_paxban = None
    paxban_gtm = None
    to_gtm = None
    for nombre, poly in dict_concesiones.items():
        if "Paxbán" in nombre:
            poly_paxban = poly
            break
    
    if poly_paxban and Transformer:
        try:
            # Definiciones de proyección
            proj_wgs84 = "EPSG:4326"
            proj_gtm = "+proj=tmerc +lat_0=15.83333333333333 +lon_0=-90.33333333333333 +k=0.9998 +x_0=500000 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            
            to_gtm = Transformer.from_crs(proj_wgs84, proj_gtm, always_xy=True).transform
            to_wgs84 = Transformer.from_crs(proj_gtm, proj_wgs84, always_xy=True).transform
            
            paxban_gtm = transform(to_gtm, poly_paxban)
            buffer_gtm = paxban_gtm.buffer(10000) # 10,000 metros = 10 km
            zona_pre_alerta = transform(to_wgs84, buffer_gtm)
            print("✅ Zona de pre-alerta (10km) calculada correctamente.")
        except Exception as e:
            print(f"Advertencia: No se pudo calcular el buffer de pre-alerta: {e}", file=sys.stderr)

    satelites = ["MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"]
    intervalo = "3"
    base_datos = []
    area = "-94,13.5,-88,20"

    for sat in satelites:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/{area}/{intervalo}"
        try:
            print(f"Descargando datos de {sat}...")
            res = requests.get(url, timeout=30)
            res.raise_for_status()
            
            lineas = res.text.strip().split('\n')
            if len(lineas) > 1:
                for linea in lineas[1:]:
                    try:
                        col = linea.split(',')
                        if len(col) < 7: continue # Necesitamos hasta la columna 6 (acq_time)
                        lat, lon = float(col[0]), float(col[1])
                        punto_incendio = Point(lon, lat)
                        
                        nombre_concesion_afectada = None
                        esta_dentro = False
                        
                        for nombre, poligono in dict_concesiones.items():
                            if poligono.contains(punto_incendio):
                                esta_dentro = True
                                nombre_concesion_afectada = nombre
                                break
                        
                        # Verificar Pre-Alerta (Cercanía a Paxbán)
                        es_pre_alerta = False
                        distancia_str = ""
                        if zona_pre_alerta and zona_pre_alerta.contains(punto_incendio):
                            # Si está en el buffer pero NO dentro de Paxbán (para no duplicar alertas)
                            if not (nombre_concesion_afectada and "Paxbán" in nombre_concesion_afectada):
                                es_pre_alerta = True
                                # Calcular distancia exacta al límite en metros
                                if paxban_gtm and to_gtm:
                                    try:
                                        punto_gtm = transform(to_gtm, punto_incendio)
                                        dist_m = paxban_gtm.distance(punto_gtm)
                                        distancia_str = f"{int(dist_m)} m"
                                    except Exception:
                                        pass
                        
                        # Procesar fecha y hora para calcular antigüedad
                        fecha_str = col[5] # YYYY-MM-DD
                        hora_str = col[6]  # HHMM
                        # Formatear hora a HH:MM
                        if len(hora_str) == 3: hora_str = "0" + hora_str
                        if len(hora_str) != 4: hora_str = "0000"
                        
                        fecha_hora_obj = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H%M")
                        horas_pasadas = (datetime.utcnow() - fecha_hora_obj).total_seconds() / 3600
                        
                        # Determinar color según antigüedad
                        color = "blue" # Por defecto 7 días
                        if horas_pasadas <= 24:
                            color = "red"
                        elif horas_pasadas <= 48:
                            color = "orange"
                        elif horas_pasadas <= 72: # 3 días
                            color = "yellow"
                        
                        # Calcular GTM para el JSON
                        coords_gtm = convertir_a_gtm(lon, lat)

                        base_datos.append({
                            "lat": lat, 
                            "lon": lon, 
                            "alerta": esta_dentro,
                            "pre_alerta": es_pre_alerta,
                            "distancia": distancia_str,
                            "concesion": nombre_concesion_afectada if esta_dentro else "Fuera de concesión",
                            "sat": sat, 
                            "fecha": f"{fecha_str} {hora_str} UTC",
                            "horas": horas_pasadas,
                            "color": color,
                            "gtm": coords_gtm
                        })
                    except (ValueError, IndexError) as e:
                        print(f"Advertencia: Saltando línea con datos inválidos: {linea} | Error: {e}", file=sys.stderr)
                        continue
        except requests.exceptions.RequestException as e:
            print(f"Error al contactar la API para {sat}: {e}", file=sys.stderr)
            continue

    if not base_datos:
        print("Advertencia: No se encontraron datos de incendios en el área seleccionada. Se generará un reporte vacío.", file=sys.stderr)

    with open('incendios.json', 'w', encoding='utf-8') as f:
        json.dump(base_datos, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Proceso finalizado. {len(base_datos)} puntos analizados.")
    
    alertas = [p for p in base_datos if p['alerta']]
    pre_alertas = [p for p in base_datos if p.get('pre_alerta')]
    print(f"🔥 Se detectaron {len(alertas)} focos de incendio dentro de concesiones.")
    print(f"⚠️ Se detectaron {len(pre_alertas)} focos en zona de pre-alerta (10km).")

    force_report = os.environ.get("FORCE_REPORT", "false").lower() == "true"

    if alertas or pre_alertas:
        # Generar imagen del mapa para la alerta (mostrando contexto)
        imagen_bytes = generar_mapa_imagen(base_datos, dict_concesiones)
        
        # --- Guardar en Bitácora para Reporte Mensual ---
        if alertas: guardar_bitacora(imagen_bytes, "alertas", alertas)
        if pre_alertas: guardar_bitacora(imagen_bytes, "pre_alertas", pre_alertas)
        
        # --- Notificación por Telegram ---
        mensaje_telegram = "<b>🔥 Alerta Paxbán 🔥</b>\n"
        
        if alertas:
            mensaje_telegram += f"\n<b>🚨 INCENDIOS CONFIRMADOS ({len(alertas)})</b>\n"
            for a in sorted(alertas, key=lambda x: x['concesion'])[:10]:
                mensaje_telegram += f"• <b>{a['concesion']}</b>\n"
                mensaje_telegram += f"  📍 {a['gtm']}\n"
                mensaje_telegram += f"  🛰 {a['sat']} ({a['horas']:.1f}h)\n"
            if len(alertas) > 10:
                mensaje_telegram += f"<i>... y {len(alertas)-10} más.</i>\n"

        if pre_alertas:
            mensaje_telegram += f"\n<b>⚠️ PRE-ALERTAS 10km ({len(pre_alertas)})</b>\n"
            for p in sorted(pre_alertas, key=lambda x: x['distancia'])[:10]:
                mensaje_telegram += f"• <b>{p['distancia']} de Paxbán</b>\n"
                mensaje_telegram += f"  📍 {p['gtm']}\n"
                mensaje_telegram += f"  🛰 {p['sat']} ({p['horas']:.1f}h)\n"
            if len(pre_alertas) > 10:
                mensaje_telegram += f"<i>... y {len(pre_alertas)-10} más.</i>\n"
        
        mensaje_telegram += "\n<i>Ver mapa adjunto y correo para más detalles.</i>"
        enviar_alerta_telegram(mensaje_telegram, imagen_bytes)
        # --- Fin Notificación por Telegram ---

        # Reconstruyendo con f-string para simplicidad
        cuerpo_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }}
                h2 {{ color: #d32f2f; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 0.9em; }}
                th, td {{ border: 1px solid #dddddd; text-align: left; padding: 10px; }}
                th {{ background-color: #f2f2f2; }}
                .map-container {{ text-align: center; margin: 20px 0; }}
                img {{ max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <h2>🚨 Alerta de Incendios en Concesiones Forestales</h2>
            <p>Se han detectado actividad de fuego relevante para el monitoreo.</p>
            
            <div class="map-container">
                <p><strong>Ubicación de las alertas:</strong></p>
                <img src="cid:mapa_peten" alt="Mapa de Alerta">
            </div>

            """
        
        if alertas:
            cuerpo_html += f"""
            <h3>🔥 Incendios CONFIRMADOS dentro de Concesiones ({len(alertas)})</h3>
            <table>
                <tr>
                    <th>Concesión</th>
                    <th>Coordenadas GTM</th>
                    <th>Lat/Lon</th>
                    <th>Satélite</th>
                    <th>Antigüedad</th>
                    <th>Fecha (UTC)</th>
                </tr>
        """

        for alerta in alertas:
            cuerpo_html += f"""
                <tr>
                    <td><strong>{alerta['concesion']}</strong></td>
                    <td>{alerta['gtm']}</td>
                    <td>{alerta['lat']:.4f}, {alerta['lon']:.4f}</td>
                    <td>{alerta['sat']}</td>
                    <td>{alerta['horas']:.1f} horas</td>
                    <td>{alerta['fecha']}</td>
                </tr>
            """
        cuerpo_html += "</table>"

        if pre_alertas:
            cuerpo_html += f"""
            <h3 style="color: #f57c00;">⚠️ PRE-ALERTAS en zona de seguridad (10km) ({len(pre_alertas)})</h3>
            <table>
                <tr>
                    <th>Distancia a Paxbán</th>
                    <th>Coordenadas GTM</th>
                    <th>Lat/Lon</th>
                    <th>Satélite</th>
                    <th>Antigüedad</th>
                    <th>Fecha (UTC)</th>
                </tr>
            """
            for pre_alerta in sorted(pre_alertas, key=lambda x: x['distancia']):
                cuerpo_html += f"""
                    <tr>
                        <td><strong>{pre_alerta['distancia']}</strong></td>
                        <td>{pre_alerta['gtm']}</td>
                        <td>{pre_alerta['lat']:.4f}, {pre_alerta['lon']:.4f}</td>
                        <td>{pre_alerta['sat']}</td>
                        <td>{pre_alerta['horas']:.1f} horas</td>
                        <td>{pre_alerta['fecha']}</td>
                    </tr>
                """
            cuerpo_html += "</table>"

        cuerpo_html += """
            <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                <a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #2e7d32; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">📂 Ver Galería de Descargas</a>
            </div>
            <p style="font-size: 0.9em; color: #555; margin-top: 20px;">
                Este es un mensaje de alerta automática del Sistema Paxbán.<br>
                Verifique la situación en campo.
                <br><em>Desarrollado por JR23CR</em>
            </p>
        </body>
        </html>
        """
        enviar_correo_alerta(cuerpo_html, imagen_mapa=imagen_bytes)
    elif force_report:
        print("ℹ️ No hay alertas, pero se enviará reporte de estado por solicitud manual.")

        # Generar la imagen del mapa con TODOS los puntos detectados
        imagen_bytes = generar_mapa_imagen(base_datos, dict_concesiones)

        # --- Guardar copia local y generar galería WEB ---
        guardar_mapa_local(imagen_bytes)
        generar_galeria_html()

        # --- Notificación por Telegram para reporte manual ---
        fecha_actual_telegram = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")
        mensaje_telegram = f"<b>✅ Reporte de Monitoreo Paxbán</b>\n\n"
        mensaje_telegram += f"No se han detectado amenazas directas. Estado a las {fecha_actual_telegram}.\n"
        mensaje_telegram += f"Puntos analizados en la región: {len(base_datos)}."
        enviar_alerta_telegram(mensaje_telegram, imagen_bytes)
        # --- Fin Notificación por Telegram ---
        
        fecha_actual = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M")

        cuerpo_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; }}
                .header {{ background-color: #2e7d32; color: white; padding: 15px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 20px; }}
                .status-box {{ background-color: #f1f8e9; border-left: 5px solid #2e7d32; padding: 15px; margin: 20px 0; }}
                .footer {{ font-size: 0.8em; text-align: center; color: #777; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; }}
                h2 {{ margin: 0; font-size: 1.4em; }}
                h3 {{ color: #2e7d32; margin-top: 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Reporte de Monitoreo Satelital</h2>
                </div>
                <div class="content">
                    <p>Estimado usuario,</p>
                    <p>El sistema <strong>Alerta Paxbán</strong> ha completado el análisis de los datos satelitales más recientes.</p>
                    
                    <div class="status-box">
                        <h3>✅ Estado: Sin Amenazas Detectadas</h3>
                        <p>No se han identificado focos de incendio activos dentro de los polígonos de las concesiones forestales monitoreadas.</p>
                        <p><strong>Puntos analizados en la región:</strong> {len(base_datos)}<br>
                        <strong>Hora del reporte:</strong> {fecha_actual}</p>
                    </div>

                    <p>A continuación, se presenta el <strong>Mapa de Situación Actual en Petén</strong>, mostrando la actividad térmica general en la región. Los colores indican la antigüedad del punto de calor (Rojo: &lt;24h, Naranja: &lt;48h, Amarillo: &lt;72h).</p>
                    
                    <div style="text-align: center; margin-top: 20px;">
                        <img src="cid:mapa_peten" alt="Mapa de Situación Petén" style="max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px;">
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <p><strong>📂 Histórico y Descargas</strong></p>
                        <p>Para descargar este mapa en alta resolución o consultar fechas anteriores:</p>
                        <a href="https://JR23CR.github.io/alerta-paxban/reportes.html" style="background-color: #2e7d32; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">⬇️ Ir a Galería de Descargas</a>
                    </div>
                </div>
                <div class="footer">
                    <p>Sistema de Alerta Temprana Paxbán<br>
                    Mensaje generado automáticamente por solicitud manual.<br>
                    <em>Desarrollado por JR23CR</em></p>
                </div>
            </div>
        </body>
        </html>
        """
        enviar_correo_alerta(cuerpo_html, asunto="Reporte de Monitoreo", imagen_mapa=imagen_bytes)

if __name__ == "__main__":
    obtener_incendios()
