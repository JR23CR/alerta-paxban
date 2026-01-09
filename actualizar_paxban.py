import requests
import json
from shapely.geometry import shape, Point

# Tu clave de NASA FIRMS
MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

# Polígono de la Concesión Paxbán
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
    # Área ampliada: cubre todo Petén y zonas de México/Belice
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-92,16,-88,18.5/1"
    
    try:
        print(f"Conectando a la NASA...")
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        
        datos_finales = []
        lineas = res.text.strip().split('\n')
        
        if len(lineas) > 1:
            for linea in lineas[1:]:
                col = linea.split(',')
                try:
                    lat, lon = float(col[0]), float(col[1])
                    punto = Point(lon, lat)
                    
                    # Detectar si está dentro de Paxbán
                    esta_dentro = paxban_poly.contains(punto)
                    
                    datos_finales.append({
                        "lat": lat,
                        "lon": lon,
                        "alerta": esta_dentro
                    })
                except: continue

        # Guardar el JSON (esto es lo que lee el index.html)
        with open('incendios.json', 'w', encoding='utf-8') as f:
            json.dump(datos_finales, f, indent=2)
        
        print(f"✅ Éxito: {len(datos_finales)} puntos guardados.")
        return len(datos_finales)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

if __name__ == "__main__":
    obtener_incendios()
