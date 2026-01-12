import requests
import json
from shapely.geometry import shape, Point
from datetime import datetime
import sys
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pyproj import Transformer

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

def convertir_a_gtm(lon, lat):
    """Convierte coordenadas de WGS84 (lat, lon) a GTM."""
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

def enviar_correo_alerta(cuerpo_html, asunto="🔥 Alerta Temprana de Incendio en Concesión Forestal"):
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

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("✅ Correo de alerta enviado exitosamente.")
    except Exception as e:
        print(f"Error crítico: No se pudo enviar el correo de alerta. Causa: {e}", file=sys.stderr)


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
    intervalo = "7" # Cambiado a 7 días como solicitaste
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
        
        # Obtener hasta 5 incendios fuera de concesiones como referencia
        externos = [p for p in base_datos if not p['alerta']][:5]
        
        html_externos = ""
        if externos:
            html_externos = """
            <h3>🔥 Últimos focos detectados fuera de concesiones (Referencia)</h3>
            <p>Estos puntos se detectaron en la región pero <strong>fuera</strong> de las áreas monitoreadas:</p>
            <table>
                <tr>
                    <th>Coordenadas Lat/Lon</th>
                    <th>Fecha</th>
                    <th>Satélite</th>
                </tr>
            """
            for ext in externos:
                html_externos += f"""
                <tr>
                    <td>{ext['lat']:.4f}, {ext['lon']:.4f}</td>
                    <td>{ext['fecha']}</td>
                    <td>{ext['sat']}</td>
                </tr>
                """
            html_externos += "</table>"

        cuerpo_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
                th, td {{ border: 1px solid #dddddd; text-align: left; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h2>✅ Reporte de Estado: Sin Incendios en Concesiones</h2>
            <p>El monitoreo manual no ha detectado focos de incendio <strong>dentro</strong> de las concesiones forestales en este momento.</p>
            <p>Se analizaron un total de <strong>{len(base_datos)}</strong> puntos de calor en toda la región descargada.</p>
            {html_externos}
            <p style="margin-top: 20px; font-size: 0.9em; color: #555;">Este es un correo generado por solicitud manual (Run Workflow).</p>
        </body>
        </html>
        """
        enviar_correo_alerta(cuerpo_html, asunto="✅ Reporte de Estado: Sin Incendios en Concesiones")

if __name__ == "__main__":
    obtener_incendios()
