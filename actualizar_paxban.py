import os
import sys
import json
import smtplib
from datetime import datetime, timedelta
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import requests
from shapely.geometry import shape, Point
from shapely.ops import transform

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

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("✅ Correo de alerta enviado exitosamente.")
    except Exception as e:
        print(f"Error crítico: No se pudo enviar el correo de alerta. Causa: {e}", file=sys.stderr)

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

        cuerpo_html = """
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }
                h2 { color: #d32f2f; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 0.9em; }
                th, td { border: 1px solid #dddddd; text-align: left; padding: 10px; }
                th { background-color: #f2f2f2; }
                .map-container { text-align: center; margin: 20px 0; }
                img { max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px; }
            </style>
        </head>
        <body>
            <h2>🚨 Alerta de Incendios en Concesiones Forestales</h2>
            <p>Se han detectado <strong>{len(alertas)}</strong> focos de incendio activos dentro de las áreas monitoreadas.</p>
            
            <div class="map-container">
                <img src="cid:mapa_peten" alt="Mapa de Alerta">
            </div>

            <table>
                <tr>
                    <th>Concesión</th>
                    <th>Distancia a Paxbán</th>
                    <th>Coordenadas GTM</th>
                    <th>Lat/Lon</th>
                    <th>Satélite</th>
                    <th>Antigüedad</th>
                    <th>Fecha (UTC)</th>
                </tr>
        """.format(len=len) # Usar format para len(alertas) si es necesario, o f-string arriba
        
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
        cuerpo_html += """
            </table>
            <p style="font-size: 0.9em; color: #666; margin-top: 20px;">
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
