import requests
import json
from shapely.geometry import shape, Point

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

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
    # Lista de satélites para máxima cobertura:
    # 1. SUOMI_VIIRS_C2 (Muy preciso)
    # 2. J1_VIIRS_C2 (Satélite NOAA-20, complementario)
    satelites = ["SUOMI_VIIRS_C2", "J1_VIIRS_C2"]
    dias = "2" # "1" para 24h, "2" para 48h
    
    puntos_totales = []
    
    for sat in satelites:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/-93,14,-88,19/{dias}"
        try:
            print(f"Consultando satélite {sat}...")
            res = requests.get(url, timeout=30)
            if res.status_code == 200:
                lineas = res.text.strip().split('\n')
                if len(lineas) > 1:
                    for linea in lineas[1:]:
                        col = linea.split(',')
                        lat, lon = float(col[0]), float(col[1])
                        esta_dentro = paxban_poly.contains(Point(lon, lat))
                        puntos_totales.append({
                            "lat": lat, "lon": lon, 
                            "alerta": esta_dentro,
                            "sat": sat # Guardamos qué satélite lo vio
                        })
        except: continue

    with open('incendios.json', 'w', encoding='utf-8') as f:
        json.dump(puntos_totales, f, indent=2)
    
    print(f"✅ Proceso terminado. Se encontraron {len(puntos_totales)} puntos en total.")

if __name__ == "__main__":
    obtener_incendios()
