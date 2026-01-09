import requests
import json
from shapely.geometry import shape, Point

# Tu configuración
MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"
# Coordenadas exactas de tu archivo GeoJSON
paxban_coords = [
    [-90.331687916, 17.812255856], [-90.333465643, 17.812208597], 
    [-90.377677966, 17.811534718], [-90.384658792, 17.811743326], 
    [-90.378196784, 17.601888474], [-90.327545166, 17.626940245], 
    [-90.259407068, 17.639806693], [-90.144088747, 17.701276745], 
    [-89.999824469, 17.725458611], [-89.999610819, 17.814877956],
    [-90.000114507, 17.814878121], [-90.331687916, 17.812255856]
]
paxban_poly = shape({"type": "Polygon", "coordinates": [paxban_coords]})

def obtener_incendios():
    # Consultamos el área de Petén (Bounding Box aproximado)
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-91,16,-89,19/1"
    res = requests.get(url)
    incendios_en_paxban = []

    if res.status_code == 200:
        lineas = res.text.strip().split('\n')[1:]
        for linea in lineas:
            d = linea.split(',')
            lat, lon = float(d[0]), float(d[1])
            if paxban_poly.contains(Point(lon, lat)):
                incendios_en_paxban.append({"lat": lat, "lon": lon, "br": d[2]})
    
    # Guardamos el resultado para que el mapa lo lea
    with open('incendios.json', 'w') as f:
        json.dump(incendios_en_paxban, f)
    print(f"Proceso terminado. Incendios encontrados: {len(incendios_en_paxban)}")

if __name__ == "__main__":
    obtener_incendios()
