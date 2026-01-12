import requests
import json
from shapely.geometry import shape, Point
from datetime import datetime

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

def cargar_concesiones(archivo_geojson):
    """Carga todas las áreas del GeoJSON en un diccionario de objetos Shapely."""
    concesiones = {}
    with open(archivo_geojson, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for feature in data['features']:
            # Extraemos el nombre de la propiedad 'Name' que vimos en tu archivo
            nombre = feature['properties'].get('Name', 'Área desconocida')
            # Convertimos la geometría a un objeto shape de Shapely
            concesiones[nombre] = shape(feature['geometry'])
    return concesiones

def obtener_incendios():
    # 1. Cargamos todas las concesiones del archivo que subiste
    dict_concesiones = cargar_concesiones('concesiones1.geojson')
    print(f"Cargadas {len(dict_concesiones)} concesiones para monitoreo.")

    satelites = ["MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"]
    intervalo = "3" 
    base_datos = []
    
    # Área: Norte de Guatemala y Petén
    area = "-94,13.5,-88,20"
    
    for sat in satelites:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/{area}/{intervalo}"
        try:
            print(f"Descargando datos de {sat}...")
            res = requests.get(url, timeout=30)
            if res.status_code == 200:
                lineas = res.text.strip().split('\n')
                if len(lineas) > 1:
                    for linea in lineas[1:]:
                        col = linea.split(',')
                        lat, lon = float(col[0]), float(col[1])
                        punto_incendio = Point(lon, lat)
                        
                        # 2. Verificamos contra TODAS las concesiones
                        nombre_concesion_afectada = None
                        esta_dentro = False
                        
                        for nombre, poligono in dict_concesiones.items():
                            if poligono.contains(punto_incendio):
                                esta_dentro = True
                                nombre_concesion_afectada = nombre
                                break # Si ya lo encontró en una, saltamos a la siguiente alerta
                        
                        base_datos.append({
                            "lat": lat, 
                            "lon": lon, 
                            "alerta": esta_dentro,
                            "concesion": nombre_concesion_afectada if esta_dentro else "Fuera de concesión",
                            "sat": sat,
                            "fecha": col[5]
                        })
        except Exception as e:
            print(f"Error en {sat}: {e}")
            continue

    with open('incendios.json', 'w', encoding='utf-8') as f:
        json.dump(base_datos, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Proceso finalizado. {len(base_datos)} puntos analizados.")
    # Mostrar resumen de alertas reales
    alertas = [p for p in base_datos if p['alerta']]
    print(f"🔥 Se detectaron {len(alertas)} focos de incendio dentro de concesiones.")

if __name__ == "__main__":
    obtener_incendios()
