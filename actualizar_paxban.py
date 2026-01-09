import requests
import json
from shapely.geometry import shape, Point

MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

# Coordenadas de Paxbán
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
    # Consultamos los 3 satélites VIIRS para no perder ningún detalle
    satelites = ["SUOMI_VIIRS_C2", "J1_VIIRS_C2", "J2_VIIRS_C2"]
    intervalo = "2" # "2" significa últimas 48 horas para que el mapa se vea lleno
    
    todos_los_puntos = []
    
    for sat in satelites:
        # Área amplia de Petén y alrededores
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sat}/-92,16,-89,18.5/{intervalo}"
        try:
            res = requests.get(url, timeout=30)
            if res.status_code == 200:
                lineas = res.text.strip().split('\n')
                if len(lineas) > 1:
                    for linea in lineas[1:]:
                        col = linea.split(',')
                        lat, lon = float(col[0]), float(col[1])
                        # Verificamos si cae en Paxbán
                        es_paxban = paxban_poly.contains(Point(lon, lat))
                        todos_los_puntos.append({
                            "lat": lat, "lon": lon, 
                            "alerta": es_paxban,
                            "sat": sat
                        })
        except: continue

    with open('incendios.json', 'w', encoding='utf-8') as f:
        json.dump(todos_los_puntos, f, indent=2)
    
    print(f"✅ ¡Barrido completo! {len(todos_los_puntos)} puntos detectados.")

if __name__ == "__main__":
    obtener_incendios()
