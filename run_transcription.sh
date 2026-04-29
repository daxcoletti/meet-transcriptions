#!/bin/bash
PROJECT_DIR="/home/dax/dev/meet-transcriptions"

# Activar el entorno virtual
source "$PROJECT_DIR/venv/bin/activate"

# Ejecutar el script (usamos la ruta completa del log para debug)
python "$PROJECT_DIR/super_transcriptor_v2.py" >> "/home/dax/Audios/cron_log.log" 2>&1

# Salir del entorno
deactivate
