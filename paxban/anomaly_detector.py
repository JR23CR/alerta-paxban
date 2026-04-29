import os
import requests
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger("PaxbanSystem")

class AnomalyDetector:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        self.process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
        
        # Cargar el polígono de Paxbán real dinámicamente
        self.paxban_poly = None
        self.bbox_paxban = None
        
        try:
            import json
            from shapely.geometry import shape
            with open("concesiones1.geojson", "r", encoding="utf-8") as f:
                concesiones_data = json.load(f)
                for feature in concesiones_data.get("features", []):
                    # La propiedad correcta es 'Name'
                    nombre = str(feature.get("properties", {}).get("Name", "")).upper()
                    if "PAXBAN" in nombre or "PAXBÁN" in nombre:
                        self.paxban_poly = shape(feature["geometry"])
                        self.bbox_paxban = list(self.paxban_poly.bounds) # (minx, miny, maxx, maxy)
                        break
        except Exception as e:
            logger.error(f"Error cargando polígono de Paxbán: {e}")
            
        self.token = None

    def authenticate(self):
        """Obtiene un token de acceso seguro de Copernicus Data Space."""
        logger.info("Autenticando con llaves maestras en Copernicus...")
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        resp = requests.post(self.auth_url, data=data)
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
            logger.info("Autenticación exitosa. Token obtenido.")
            return True
        else:
            logger.error(f"Fallo de autenticación OAuth: {resp.text}")
            return False

    def check_for_deforestation(self):
        """
        Utiliza la Process API y un Evalscript matemático para analizar la 
        densidad de clorofila (NDVI) real y aislar píxeles de deforestación.
        """
        logger.info("Iniciando escáner de precisión matemática (Statistical Evalscript)...")
        if not self.bbox_paxban:
            return {"status": "ERROR", "mensaje": "Polígono de Paxbán no encontrado en el GeoJSON."}
            
        if not self.token and not self.authenticate():
            return {"status": "ERROR", "mensaje": "Fallo de credenciales OAuth."}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # El Evalscript se ejecuta directamente en los servidores de la Agencia Espacial Europea.
        evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: ["B02", "B04", "B08", "B11", "SCL", "dataMask"],
                output: { bands: 1, sampleType: "UINT8" }
            };
        }
        function evaluatePixel(sample) {
            if ([3, 7, 8, 9, 10, 11].includes(sample.SCL)) {
                return [0]; 
            }
            if (sample.dataMask === 0) return [0];

            // Nubes extremadamente brillantes (suavizado para no borrar la tierra blanca)
            if (sample.B02 > 0.25) { return [0]; }
            
            // Sombras demasiado oscuras
            if (sample.B08 < 0.05) { return [0]; }

            // NDVI (Clorofila)
            let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
            // NDMI (Humedad usando Infrarrojo de Onda Corta B11)
            let ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
            
            // MAGIA DE TELEDETECCIÓN AVANZADA:
            // Un botado pierde casi toda su humedad instantáneamente (NDMI baja drásticamente)
            // La selva tiene NDMI > 0.3. Las nubes tienen alta reflectancia en B08 y B11 (NDMI varía pero no coincide con tierra).
            // La tierra desnuda/seca tiene NDMI < 0.15 y NDVI < 0.50.
            
            if (ndvi >= 0.05 && ndvi <= 0.50 && ndmi < 0.15) {
                return [255]; // ¡ANOMALÍA!
            }
            return [0]; 
        }
        """

        # Petición a la Process API
        payload = {
            "input": {
                "bounds": {
                    "bbox": self.bbox_paxban,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a", 
                        "dataFilter": {
                            "timeRange": {
                                "from": start_date.strftime('%Y-%m-%dT00:00:00Z'),
                                "to": end_date.strftime('%Y-%m-%dT23:59:59Z')
                            },
                            "maxCloudCoverage": 20
                        }
                    }
                ]
            },
            "output": {
                "width": 1024, 
                "height": 1024,
                "responses": [{"identifier": "default", "format": {"type": "image/png"}}]
            },
            "evalscript": evalscript
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        try:
            logger.info("Descargando matriz matemática pura (Process API)...")
            response = requests.post(self.process_url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                logger.info("Analizando píxeles binarios de deforestación y vectorizando a polígonos...")
                import numpy as np
                import cv2
                from shapely.geometry import Polygon, Point
                import json
                
                nparr = np.frombuffer(response.content, np.uint8)
                img_cv = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                
                contours, _ = cv2.findContours(img_cv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                width, height = img_cv.shape[1], img_cv.shape[0]
                min_lon, min_lat, max_lon, max_lat = self.bbox_paxban
                
                features = []
                area_total = 0
                
                for cnt in contours:
                    if cv2.contourArea(cnt) < 2:
                        continue
                        
                    poly_coords = []
                    for point in cnt:
                        x, y = point[0]
                        lon = min_lon + (x / width) * (max_lon - min_lon)
                        lat = max_lat - (y / height) * (max_lat - min_lat)
                        poly_coords.append((lon, lat))
                        
                    if len(poly_coords) >= 3:
                        poly_coords.append(poly_coords[0])
                        geom_poly = Polygon(poly_coords)
                        
                        # VERIFICAR SI ESTÁ DENTRO DE PAXBAN
                        if self.paxban_poly and not self.paxban_poly.intersects(geom_poly):
                            continue # IGNORAR POR COMPLETO SI ESTÁ FUERA
                            
                        area_total += cv2.contourArea(cnt) * 0.01 
                        
                        features.append({
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [poly_coords]
                            },
                            "properties": {
                                "type": "botado_confirmado",
                                "date": end_date.strftime('%Y-%m-%d')
                            }
                        })
                
                if features: 
                    logger.warning(f"¡PELIGRO! Se detectaron {len(features)} polígonos anómalos confirmados dentro de Paxbán.")
                    
                    geojson = {"type": "FeatureCollection", "features": features}
                    with open("anomalias.geojson", "w") as f:
                        json.dump(geojson, f)
                    
                    centroide = features[0]["geometry"]["coordinates"][0][0]
                    return {
                        "status": "DANGER",
                        "tipo": "Tala/Botado Confirmado (Alta Precisión)",
                        "area_ha": round(area_total, 2),
                        "coordenadas": f"{centroide[1]:.5f}, {centroide[0]:.5f}",
                        "mensaje": f"Anomalía severa detectada. Bordes exactos dibujados en el visor."
                    }
                else:
                    logger.info("Análisis completado. Bosque de Paxbán 100% íntegro en las últimas tomas.")
                    if os.path.exists("anomalias.geojson"):
                        os.remove("anomalias.geojson")
                    return {"status": "OK", "mensaje": "Sin deforestación detectada en Paxbán."}
            else:
                logger.error(f"Error en Copernicus API: {response.text}")
                return {"status": "ERROR", "mensaje": "Fallo en la API Espacial."}
                
        except Exception as e:
            logger.error(f"Error procesando imagen: {e}")
            return {"status": "ERROR", "mensaje": str(e)}
