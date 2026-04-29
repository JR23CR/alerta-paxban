import re
import os

file_path = 'actualizar_paxban.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Eliminar emojis de las líneas que contienen 'print'
def remove_emojis(match):
    line = match.group(0)
    # Mantener solo caracteres ASCII básicos en los prints de consola
    return re.sub(r'[^\x00-\x7F]', '', line)

# Buscar llamadas a print y limpiar su contenido
new_content = re.sub(r'print\(.*?\)', remove_emojis, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Limpieza de emojis completada.")
