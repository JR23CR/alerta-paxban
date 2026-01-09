import requests
import json
from shapely.geometry import shape, Point

# Configuración
MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

# Coordenadas de Paxbán para el filtro
paxban_coords = [
    [-90.33168791599998, 17.81225585600004], [-90.33346564299997, 17.81220859700005],
    [-90.37767796599996, 17.81153471800008], [-90.384658792, 17.81174332600006],
    [-90.37819678399995, 17.60188847400008], [-90.32754516599992, 17.62694024500007],
    [-90.25940706799997, 17.63980669300003], [-90.14408874699996, 17.70127674500003],
    [-89.99982446899998, 17.72545861100002], [-89.99961081899994, 17.81487795600003],
    [-90.00011450699998, 17.81487812100005], [-90.33168791599998, 17.81225585600004]
]

paxban_poly = shape({"type": "Polygon", "coordinates": [paxban_coords]})

def obtener_incendios():
    # Consultamos un área más grande de Petén (-91 a -89 longitud)
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-91,17,-89,18.5/1"
    
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        
        todos_los_puntos = []
        lineas = res.text.strip().split('\n')
        
        if len(lineas) > 1:
            for linea in lineas[1:]:
                datos = linea.split(',')
                try:
                    lat, lon = float(datos[0]), float(datos[1])
                    punto = Point(lon, lat)
                    
                    # LA CLAVE: Marcamos si está en Paxbán o no
                    es_paxban = paxban_poly.contains(punto)
                    
                    todos_los_puntos.append({
                        "lat": lat, "lon": lon,
                        "alerta": es_paxban
                    })
                except: continue

        with open('incendios.json', 'w', encoding='utf-8') as f:
            json.dump(todos_los_puntos, f, indent=2)
        
        print(f"✅ Datos actualizados. Total puntos: {len(todos_los_puntos)}")
        return len(todos_los_puntos)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

if __name__ == "__main__":
    obtener_incendios()
