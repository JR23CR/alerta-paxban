import requests
import json
from shapely.geometry import shape, Point
from datetime import datetime

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

# Límites de Paxbán
paxban_coords = [[-90.3316, 17.8122], [-90.3776, 17.8115], [-90.3846, 17.8117], [-90.3781, 17.6018], [-90.3275, 17.6269], [-90.2594, 17.6398], [-90.1440, 17.7012], [-89.9998, 17.7254], [-89.9996, 17.8148], [-90.3316, 17.8122]]
paxban_poly = shape({"type": "Polygon", "coordinates": [paxban_coords]})

def obtener_incendios():
    satelites = ["SUOMI_VIIRS_C2", "J1_VIIRS_C2", "J2_VIIRS_C2"]
    # Pedimos 3 días para tener historial para los filtros
    intervalo = "3" 
    base_datos = []
    
    for sat in satelites:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/-92,16,-89,19/{intervalo}"
        try:
            res = requests.get(url, timeout=30)
            if res.status_code == 200:
                lineas = res.text.strip().split('\n')
                if len(lineas) > 1:
                    for linea in lineas[1:]:
                        col = linea.split(',')
                        lat, lon = float(col[0]), float(col[1])
                        # Extraer fecha para el filtro del mapa
                        fecha_str = col[5] # formato YYYY-MM-DD
                        
                        esta_dentro = paxban_poly.contains(Point(lon, lat))
                        base_datos.append({
                            "lat": lat, "lon": lon, 
                            "alerta": esta_dentro,
                            "sat": sat,
                            "fecha": fecha_str
                        })
        except: continue

    with open('incendios.json', 'w', encoding='utf-8') as f:
        json.dump(base_datos, f, indent=2)
    print(f"✅ Base de datos actualizada con {len(base_datos)} puntos.")

if __name__ == "__main__":
    obtener_incendios()
