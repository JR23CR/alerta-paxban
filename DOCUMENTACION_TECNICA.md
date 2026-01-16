# Documentación Técnica: Sistema de Alerta Paxbán

## 1. Visión General
El **Sistema de Alerta Paxbán** es una solución tecnológica automatizada diseñada para la vigilancia continua, detección temprana y reporte de incendios forestales en la Concesión Industrial Paxbán y áreas aledañas en Petén, Guatemala. Integra datos satelitales en tiempo real con análisis geoespacial preciso.

## 2. Arquitectura del Sistema
El software opera bajo una arquitectura **Serverless** (sin servidor dedicado), aprovechando la infraestructura de nube de GitHub.

*   **Lenguaje de Programación:** Python 3.9
*   **Orquestación y Automatización:** GitHub Actions
*   **Visualización Web:** GitHub Pages
*   **Fuentes de Datos:** API de NASA FIRMS (Sensores MODIS y VIIRS).

### Flujo de Datos
1.  **Adquisición:** Un cron job ejecuta el script cada hora. Se descargan datos CSV de la NASA.
2.  **Procesamiento Geoespacial:**
    *   Se cruzan los puntos de calor con los polígonos de `concesiones1.geojson` usando la librería `Shapely`.
    *   Se transforman coordenadas (WGS84 a GTM) usando `Pyproj` para precisión métrica.
    *   Se calculan distancias a campamentos (`campamentos.json`) y límites fronterizos.
3.  **Generación de Productos:**
    *   Mapas visuales (PNG) generados con `Matplotlib` y `Contextily`.
    *   Reportes en formato Word (`python-docx`).
    *   Actualización de base de datos ligera (`incendios.json`).
4.  **Distribución:** Envío de alertas por Correo Electrónico (SMTP) y Telegram.
5.  **Despliegue:** Reconstrucción automática del sitio web de reportes.

## 3. Componentes Principales

### 3.1 Script Core (`actualizar_paxban.py`)
Es el cerebro del sistema. Sus módulos clave son:
*   **`convertir_a_gtm`**: Convierte coordenadas globales a la proyección local de Guatemala para facilitar la navegación terrestre.
*   **`calcular_distancia_direccion`**: Algoritmo geométrico que determina qué tan lejos está un incendio del límite de la concesión y en qué dirección.
*   **`generar_mapa_imagen`**: Crea imágenes estáticas del mapa situacional sobre una base cartográfica de National Geographic.
*   **`enviar_correo_alerta`**: Gestor de notificaciones que construye correos HTML dinámicos con tablas de datos y mapas adjuntos.
*   **`main`**: Controlador lógico que decide si se activa una Alerta Roja (incendio interno), Pre-Alerta (zona de amortiguamiento) o Reporte de Estado.

### 3.2 Flujo de Trabajo (`.github/workflows/static.yml`)
Define la infraestructura como código (IaC):
*   **Triggers:** Ejecución programada (cron) y manual (`workflow_dispatch`).
*   **Entorno:** Configura un servidor Ubuntu efímero, instala librerías geoespaciales (GEOS) y dependencias de Python.
*   **Persistencia:** Realiza commits automáticos al repositorio para guardar el historial de mapas y bitácoras.

## 4. Tecnologías y Librerías
*   **Requests:** Comunicación con APIs externas.
*   **Shapely:** Análisis geométrico (Punto en Polígono, Intersecciones).
*   **Pyproj:** Proyecciones cartográficas.
*   **Matplotlib & Contextily:** Visualización de datos y mapas base.
*   **Python-docx:** Generación automatizada de informes ofimáticos.

## 5. Seguridad y Configuración
El sistema utiliza "Secretos de GitHub" para proteger credenciales sensibles:
*   Credenciales SMTP (Correo).
*   Tokens de Bots de Telegram.
*   Claves de API de Mapas.

## 6. Mantenimiento
El sistema es autónomo. El mantenimiento se limita a:
*   Actualización de polígonos en `concesiones1.geojson` si cambian los límites legales.
*   Actualización de la lista de `campamentos.json`.
*   Revisión de cuotas de la API de la NASA.