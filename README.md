# Sistema de Alerta Temprana y Monitoreo de Incendios Forestales - Paxbán

## Descripción General

El **Sistema de Alerta Paxbán** es una solución tecnológica automatizada diseñada para la vigilancia continua, detección temprana y reporte de incendios forestales en la Concesión Industrial Paxbán y sus áreas de influencia en la Reserva de la Biosfera Maya, Petén, Guatemala.

Este software opera en la nube integrando datos satelitales en tiempo real con análisis geoespacial preciso para proporcionar a los gestores forestales información crítica para la toma de decisiones y la respuesta rápida ante amenazas de fuego.

## Funcionalidades Principales

### 1. Monitoreo Satelital Multiespectral
*   **Integración NASA FIRMS**: Conexión directa con el sistema de información sobre incendios de la NASA.
*   **Sensores**: Procesa datos de los sensores **MODIS** y **VIIRS** (S-NPP y NOAA-20), permitiendo una detección de alta resolución temporal y espacial.
*   **Cobertura**: Monitoreo continuo de la región de Petén con actualizaciones horarias.

### 2. Análisis Geoespacial y Detección de Amenazas
*   **Alertas Confirmadas**: Algoritmos geométricos verifican si un punto de calor se encuentra dentro del polígono oficial de la concesión Paxbán.
*   **Pre-Alertas (Zona de Seguridad)**: Sistema de vigilancia perimetral que detecta incendios en un radio de **10 kilómetros** alrededor de la concesión.
*   **Cálculo de Distancias**: Determina automáticamente la distancia lineal exacta (en metros) desde el foco del incendio hasta el límite más cercano de la concesión.
*   **Proyección GTM**: Conversión automática de coordenadas geográficas a **GTM (Guatemala Transversal Mercator)** para facilitar la navegación terrestre de las cuadrillas.

### 3. Sistema de Notificaciones Inteligentes
*   **Alertas por Correo Electrónico**: Envío automático de reportes detallados al detectar amenazas.
*   **Reportes Visuales Adjuntos**: Generación dinámica de imágenes de mapas (formato PNG) incrustadas en el correo, mostrando la ubicación del incendio sobre una base cartográfica de **National Geographic**, con la delimitación clara del área protegida.
*   **Clasificación de Urgencia**: Tablas diferenciadas para incendios internos (Alerta Roja) y externos cercanos (Pre-Alerta).

### 4. Interfaz Web de Visualización
*   **Mapa Interactivo**: Plataforma web accesible desde cualquier navegador para visualizar la situación actual.
*   **Filtros Temporales**: Capacidad de filtrar focos de calor por antigüedad (últimas 24h, 48h, 72h) con código de colores (Rojo, Naranja, Amarillo).
*   **Capas Base**: Opciones de visualización entre mapa topográfico (NatGeo), imágenes satelitales (Esri) y callejero (OSM).

---

## Arquitectura e Integración

El sistema funciona bajo una arquitectura **Serverless** (sin servidor dedicado), aprovechando la infraestructura de GitHub para garantizar alta disponibilidad y bajo costo de mantenimiento.

### Flujo de Datos
1.  **Adquisición**: Un cron job (tarea programada) en **GitHub Actions** ejecuta el script principal cada hora.
2.  **Procesamiento (Python)**:
    *   El script descarga los datos CSV más recientes de la API de la NASA.
    *   Utiliza librerías geoespaciales (`Shapely`, `Pyproj`) para cruzar los datos con el archivo `concesiones1.geojson`.
    *   Genera mapas estáticos utilizando `Matplotlib` y `Contextily`.
3.  **Distribución**:
    *   Si se detectan alertas, se utiliza el protocolo SMTP para enviar correos a través de Gmail.
    *   Se actualiza la base de datos `incendios.json`.
4.  **Despliegue**: El frontend web se reconstruye y despliega automáticamente en **GitHub Pages**.

### Tecnologías Utilizadas
*   **Lenguaje**: Python 3.9
*   **Librerías Clave**: `requests`, `shapely`, `pyproj`, `matplotlib`, `contextily`.
*   **Infraestructura**: GitHub Actions, GitHub Pages.
*   **Frontend**: HTML5, Leaflet.js.

---

## Uso del Sistema

### Modo Automático
El sistema opera de forma autónoma las 24 horas del día. No requiere intervención del usuario a menos que se reciba una alerta.

### Modo Manual (Reporte de Estado)
Los administradores pueden solicitar un reporte de estado en cualquier momento:
1.  Ir a la pestaña **"Actions"** en el repositorio.
2.  Seleccionar el flujo **"Monitor y Deploy Paxban"**.
3.  Hacer clic en **"Run workflow"**.

**Resultado**: El sistema realizará un barrido completo y enviará un correo electrónico con el asunto "Reporte de Monitoreo", incluyendo un mapa actualizado de la situación en Petén, independientemente de si hay incendios activos o no dentro de la concesión.

---

## Configuración

El sistema requiere las siguientes variables de entorno (Secretos de GitHub) para funcionar:

*   `SMTP_SERVER`: Servidor de correo (ej. smtp.gmail.com).
*   `SMTP_PORT`: Puerto (ej. 587).
*   `SMTP_USER`: Correo electrónico del remitente.
*   `SMTP_PASSWORD`: Contraseña de aplicación del correo.
*   `RECIPIENT_EMAIL`: Correo electrónico del destinatario principal.

---

**Desarrollado para la conservación y protección de los recursos naturales de Guatemala.**
**Desarrollado por JR23CR**
*Versión 2.0 - Enero 2026*