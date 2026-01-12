import os
import sys
import json
import smtplib
from datetime import datetime
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import requests
from shapely.geometry import shape, Point

# Configurar matplotlib para que funcione sin pantalla (servidor) antes de importar pyplot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt # noqa: E402
import contextily as cx # noqa: E402

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

def enviar_correo_alerta(cuerpo_html, asunto="🔥 Alerta Temprana de Incendio en Concesión Forestal", imagen_mapa=None):
    """Envía un correo electrónico de alerta usando credenciales de entorno."""
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = os.environ.get("SMTP_PORT")
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL]):
        print("Advertencia: Faltan una o más variables de entorno para el envío de correo. No se enviará la alerta.", file=sys.stderr)
        return

    # Agregar fecha y hora al asunto para diferenciar correos
    fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    asunto_completo = f"{asunto} - {fecha_hora}"

    print("Enviando correo de alerta...")
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = asunto_completo
        
        msg.attach(MIMEText(cuerpo_html, 'html', 'utf-8'))
        
        # Adjuntar imagen del mapa si existe
        if imagen_mapa:
            img = MIMEImage(imagen_mapa)
            img.add_header('Content-ID', '<mapa_peten>')
            img.add_header('Content-Disposition', 'inline', filename='mapa_peten.png')
            msg.attach(img)

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("✅ Correo de alerta enviado exitosamente.")
    except Exception as e:
        print(f"Error crítico: No se pudo enviar el correo de alerta. Causa: {e}", file=sys.stderr)

def generar_mapa_imagen(puntos):
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
        
        # Si hay puntos, graficarlos
        if xs:
            ax.scatter(xs, ys, c=colores, s=50, alpha=0.8, edgecolors='white', linewidth=1, zorder=2)
        
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
    dict_concesiones = cargar_concesiones('concesiones1.geojson')
    print(f"Cargadas {len(dict_concesiones)} concesiones para monitoreo.")

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
    print(f"🔥 Se detectaron {len(alertas)} focos de incendio dentro de concesiones.")

    force_report = os.environ.get("FORCE_REPORT", "false").lower() == "true"

    if alertas:
        cuerpo_html = """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #dddddd; text-align: left; padding: 8px; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h2>🚨 Alerta de Incendios en Concesiones Forestales</h2>
            <p>Se han detectado los siguientes focos de incendio dentro de las áreas de concesión monitoreadas:</p>
            <table>
                <tr>
                    <th>Concesión Afectada</th>
                    <th>Coordenadas GTM</th>
                    <th>Coordenadas Lat/Lon</th>
                    <th>Satélite</th>
                    <th>Fecha y Hora (UTC)</th>
                </tr>
        """
        for alerta in alertas:
            coords_gtm = convertir_a_gtm(alerta['lon'], alerta['lat'])
            cuerpo_html += f"""
                <tr>
                    <td>{alerta['concesion']}</td>
                    <td>{coords_gtm}</td>
                    <td>{alerta['lat']:.4f}, {alerta['lon']:.4f}</td>
                    <td>{alerta['sat']}</td>
                    <td>{alerta['fecha']}</td>
                </tr>
            """
        cuerpo_html += """
            </table>
            <p>Este es un correo automático. Por favor, no responder.</p>
        </body>
        </html>
        """
        enviar_correo_alerta(cuerpo_html)
    elif force_report:
        print("ℹ️ No hay alertas, pero se enviará reporte de estado por solicitud manual.")
        
        # Generar la imagen del mapa con TODOS los puntos detectados
        imagen_bytes = generar_mapa_imagen(base_datos)
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")

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
                </div>
                <div class="footer">
                    <p>Sistema de Alerta Temprana Paxbán<br>
                    Mensaje generado automáticamente por solicitud manual.</p>
                </div>
            </div>
        </body>
        </html>
        """
        enviar_correo_alerta(cuerpo_html, asunto="✅ Reporte de Monitoreo: Sin Incendios en Concesiones", imagen_mapa=imagen_bytes)

if __name__ == "__main__":
    obtener_incendios()
