import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name="PaxbanSystem", log_file="paxban.log"):
    """Configura un logger profesional con rotación de archivos y salida a consola."""
    logger = logging.getLogger(name)
    
    # Evitar agregar handlers múltiples si ya existen
    if logger.hasHandlers():
        return logger
        
    logger.setLevel(logging.DEBUG)

    # Formato profesional: [FECHA HORA] [NIVEL] - Módulo - Mensaje
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Handler para Archivo (Rotativo: max 5MB por archivo, guarda hasta 3 backups)
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG) # En archivo guardamos TODO
    file_handler.setFormatter(formatter)

    # 2. Handler para Consola
    console_handler = logging.StreamHandler(sys.stdout)
    # En consola, podemos decidir mostrar solo INFO o superior por defecto
    console_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    console_handler.setLevel(getattr(logging, console_level, logging.INFO))
    console_handler.setFormatter(formatter)

    # Agregar handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Logger global para ser importado por otros módulos
logger = setup_logger()
