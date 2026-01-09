import requests
import json
from shapely.geometry import shape, Point

# Tu configuración
MAP_KEY = "1f5837a949e2dff8572d9bb96df86898"

# Coordenadas COMPLETAS de tu archivo GeoJSON (como Polygon)
paxban_coords = [
    [-90.33168791599998, 17.81225585600004],
    [-90.33346564299997, 17.81220859700005],
    [-90.37767796599996, 17.81153471800008],
    [-90.384658792, 17.81174332600006],
    [-90.37819678399995, 17.60188847400008],
    [-90.32754516599992, 17.62694024500007],
    [-90.25940706799997, 17.63980669300003],
    [-90.14408874699996, 17.70127674500003],
    [-89.99982446899998, 17.72545861100002],
    [-89.99961081899994, 17.81487795600003],
    [-90.00011450699998, 17.81487812100005],
    [-90.01923375599993, 17.81467493100007],
    [-90.03276054999996, 17.81462450100003],
    [-90.07585140299996, 17.81446416800003],
    [-90.12934117999998, 17.81440783400006],
    [-90.15168765399996, 17.81438480400004],
    [-90.160591067, 17.81436957400007],
    [-90.16741939699995, 17.81438647300007],
    [-90.22650914999997, 17.81454089700003],
    [-90.28306577099994, 17.81358365400007],
    [-90.30273442599997, 17.81304778200007],
    [-90.33168791599998, 17.81225585600004]
]

# Crear el polígono de Paxbán
paxban_poly = shape({"type": "Polygon", "coordinates": [paxban_coords]})

def obtener_incendios():
    """
    Consulta la API de NASA FIRMS para detectar incendios en el área de Paxbán
    """
    # Bounding box amplio del área de Petén/Guatemala
    # Formato: west,south,east,north
    # Área aproximada que cubre Paxbán y alrededores
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-91,16,-89,19/1"
    
    print(f"Consultando NASA FIRMS...")
    print(f"URL: {url}")
    
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        
        incendios_en_paxban = []

        if res.status_code == 200:
            lineas = res.text.strip().split('\n')
            
            # Primera línea es el header
            if len(lineas) > 1:
                header = lineas[0]
                print(f"Header CSV: {header}")
                
                # Procesar cada línea de datos
                for linea in lineas[1:]:
                    datos = linea.split(',')
                    
                    # El formato es: latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,...
                    try:
                        lat = float(datos[0])
                        lon = float(datos[1])
                        brightness = datos[2] if len(datos) > 2 else "N/A"
                        
                        # Verificar si el punto está dentro del polígono de Paxbán
                        punto = Point(lon, lat)
                        if paxban_poly.contains(punto):
                            incendios_en_paxban.append({
                                "lat": lat,
                                "lon": lon,
                                "br": brightness
                            })
                            print(f"  ✓ Incendio detectado en Paxbán: lat={lat}, lon={lon}, brightness={brightness}")
                    except (ValueError, IndexError) as e:
                        print(f"  ⚠️  Error procesando línea: {e}")
                        continue
                
                print(f"\nTotal de puntos de calor en la región: {len(lineas) - 1}")
                print(f"Incendios dentro de Paxbán: {len(incendios_en_paxban)}")
            else:
                print("No se encontraron datos en la respuesta (solo header o vacío)")
        
        # Guardar el resultado para que el mapa lo lea
        with open('incendios.json', 'w', encoding='utf-8') as f:
            json.dump(incendios_en_paxban, f, indent=2)
        
        print(f"\n✅ Proceso completado. Archivo 'incendios.json' actualizado.")
        print(f"📊 Incendios encontrados en Paxbán: {len(incendios_en_paxban)}")
        
        return len(incendios_en_paxban)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al consultar la API de NASA FIRMS: {e}")
        # En caso de error, crear un archivo vacío
        with open('incendios.json', 'w', encoding='utf-8') as f:
            json.dump([], f)
        return 0

if __name__ == "__main__":
    obtener_incendios()
