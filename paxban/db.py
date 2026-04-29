import sqlite3
import os
from datetime import datetime
from paxban.logger import logger

DB_FILE = "historial_incendios.sqlite"

def init_db():
    """Crea la tabla histórica si no existe."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Tabla para guardar cada foco de calor detectado
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS focos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL,
            lon REAL,
            satelite TEXT,
            fecha_satelite TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            concesion TEXT,
            estado_alerta TEXT, -- ROJA, AMARILLA, VERDE
            distancia_info TEXT
        )
        ''')
        
        # Creamos un índice para buscar rápidamente por coordenadas y fecha
        # y así evitar guardar duplicados del mismo satélite en la misma pasada
        cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_foco_unico 
        ON focos (lat, lon, fecha_satelite)
        ''')
        
        conn.commit()
        conn.close()
        logger.debug("Base de datos histórica inicializada correctamente.")
    except Exception as e:
        logger.error(f"Error inicializando BD: {e}")

def guardar_focos_historicos(puntos):
    """Guarda una lista de puntos en el historial."""
    if not puntos:
        return
        
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        insertados = 0
        for p in puntos:
            estado = "ROJA" if p.get('alerta') else "AMARILLA" if p.get('pre_alerta') else "VERDE"
            try:
                cursor.execute('''
                INSERT INTO focos (lat, lon, satelite, fecha_satelite, concesion, estado_alerta, distancia_info)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p['lat'], p['lon'], p['sat'], p['fecha'], 
                    p.get('concesion', 'Desconocida'), estado, p.get('dist_info', '')
                ))
                insertados += 1
            except sqlite3.IntegrityError:
                # El foco ya estaba registrado (ignorar duplicado)
                pass
                
        conn.commit()
        conn.close()
        logger.info(f"Se agregaron {insertados} focos nuevos a la base de datos histórica.")
    except Exception as e:
        logger.error(f"Error guardando focos en BD: {e}")

# Inicializar al cargar el módulo
init_db()
