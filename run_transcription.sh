#!/bin/bash
# Wrapper para cron. La redirección de stdout/stderr al log la maneja
# quien invoca este script (ver /etc/cron.d/transcripcion_audios).
# Si lo corrés a mano, vas a ver la salida en la terminal.
PROJECT_DIR="/home/dax/dev/meet-transcriptions"

source "$PROJECT_DIR/venv/bin/activate"
python "$PROJECT_DIR/super_transcriptor_v2.py"
deactivate
