#!/usr/bin/env bash
# -------------------------------------------------------------------------
# Aigents Pulse v3.1 (Spectre+)
# Setup Systemd Service for Master Server
# -------------------------------------------------------------------------

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

if [[ "$EUID" -ne 0 ]]; then
    echo -e "${RED}ERROR:${NC} Necesita ejecutarse con privilegios de root (sudo)."
    exit 1
fi

APP_DIR=$(pwd)
USER_NAME=$(logname || echo $USER)
PYTHON_PATH=$(which python3)
VENV_PATH="${APP_DIR}/.venv/bin/python3"

# Verificar si existe el entorno virtual
if [[ -f "$VENV_PATH" ]]; then
    PYTHON_EXEC="$VENV_PATH"
else
    PYTHON_EXEC="$PYTHON_PATH"
fi

echo -e "${GREEN}⚙️ Configurando Aigents Pulse como servicio del sistema...${NC}"
echo -e "Directorio: ${YELLOW}${APP_DIR}${NC}"
echo -e "Ejecutable: ${YELLOW}${PYTHON_EXEC}${NC}"
echo -e "Usuario: ${YELLOW}${USER_NAME}${NC}"

cat > /etc/systemd/system/aigents-pulse.service <<EOF
[Unit]
Description=Aigents Pulse Infrastructure Monitoring
After=network.target

[Service]
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
Environment="PYTHONPATH=${APP_DIR}"
Environment="STREAMLIT_SERVER_PORT=8501"
Environment="STREAMLIT_SERVER_HEADLESS=true"
# Cargar .env si existe
ExecStart=${PYTHON_EXEC} -m streamlit run app.py --server.port 8501 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aigents-pulse
systemctl restart aigents-pulse

echo -e "${GREEN}✅ Servicio aigents-pulse configurado y activado.${NC}"
echo -e "Puedes ver el estado con: ${YELLOW}systemctl status aigents-pulse${NC}"
echo -e "Puedes ver los logs con: ${YELLOW}journalctl -u aigents-pulse -f${NC}"
