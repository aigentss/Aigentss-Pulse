#!/bin/bash
#
# Aigents Pulse v3.1 (Spectre+)
# Instalador automatizado de agentes (Node Exporter + cAdvisor)
# --------------------------------------------------------------
# IMPORTANTE:
#   * El script **debe ejecutarse como root** (sudo ./install.sh) o
#     con una cuenta que ya tenga privilegios de super‑usuario.
#   * Si lo ejecutas sin root, el script se abortará con un mensaje
#     explicativo para evitar los errores “cannot connect to the docker API”.
# --------------------------------------------------------------

set -euo pipefail   # Fail on error, undefined variables, y tuberías rotas

# ---------- 0️⃣  COMPROBACIÓN DE PRIVILEGIOS ----------
if [[ "$EUID" -ne 0 ]]; then
    echo -e "\n⚠️  ERROR: Este script necesita privilegios de root.\n"
    echo "Ejecuta: sudo $0   o   cambia a la cuenta root antes de iniciar."
    exit 1
fi

# ---------- 1️⃣  VARIABLES ----------
APP_NAME="Aigents Pulse"
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'   # No Color

log()   { echo -e "${GREEN}[${APP_NAME}]${NC} $*"; }
error() { echo -e "${RED}[${APP_NAME} ERROR]${NC} $*"; }

# ---------- 2️⃣  ACTUALIZAR PAQUETES ----------
log "🔄 Actualizando la lista de paquetes del sistema..."
apt-get update -y

# ---------- 3️⃣  INSTALAR DOCKER ----------
if ! command -v docker >/dev/null 2>&1; then
    log "🐳 Docker no está instalado → procediendo con la instalación..."
    
    apt-get install -y ca-certificates curl gnupg lsb-release
    
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
          https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Habilitar e iniciar el daemon
    systemctl enable --now docker
else
    log "✅ Docker ya está instalado."
fi

# ---------- 4️⃣  COMPROBAR QUE EL DAEMON ESTÁ CORRIENDO ----------
log "🔍 Verificando que Docker daemon está activo..."
if ! systemctl is-active --quiet docker; then
    error "Docker daemon no está activo. Intentando arrancarlo..."
    systemctl start docker || { error "No se pudo iniciar Docker. Revisa los logs con 'journalctl -u docker'."; exit 1; }
fi

# ---------- 5️⃣  PRUEBA BÁSICA DE DOCKER ----------
log "🧪 Ejecutando prueba rápida (hello‑world)…"
docker run --rm hello-world >/dev/null 2>&1 && log "✅ Docker funciona correctamente." || {
    error "La prueba de Docker falló. Puede que falten permisos o que el socket no exista."
    exit 1
}

# ---------- 6️⃣  INSTALAR NODE EXPORTER ----------
log "📊 Instalando Node Exporter..."
NODE_EXPORTER_VER="1.7.0"
NODE_EXPORTER_BIN="/usr/local/bin/node_exporter"

if [[ ! -x "$NODE_EXPORTER_BIN" ]]; then
    cd /tmp
    wget -q https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VER}/node_exporter-${NODE_EXPORTER_VER}.linux-amd64.tar.gz
    tar xzf node_exporter-${NODE_EXPORTER_VER}.linux-amd64.tar.gz
    cp node_exporter-${NODE_EXPORTER_VER}.linux-amd64/node_exporter "$NODE_EXPORTER_BIN"
    useradd -rs /bin/false node_exporter || true
    
    cat > /etc/systemd/system/node_exporter.service <<'EOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now node_exporter
    log "✅ Node Exporter instalado y activo (puerto 9100)."
else
    log "✅ Node Exporter ya estaba presente."
fi

# ---------- 7️⃣  DESPLEGAR CADVISOR ----------
log "🐳 Desplegando cAdvisor (Docker)…"
if ! docker ps -a --format '{{.Names}}' | grep -q '^cadvisor$'; then
    docker pull gcr.io/cadvisor/cadvisor:latest
    docker run -d \
        --name=cadvisor \
        --restart=always \
        --privileged \
        -p 8080:8080 \
        -v /:/rootfs:ro \
        -v /var/run:/var/run:ro \
        -v /sys:/sys:ro \
        -v /var/lib/docker/:/var/lib/docker:ro \
        -v /dev/disk/:/dev/disk:ro \
        gcr.io/cadvisor/cadvisor:latest
    log "✅ cAdvisor ejecutándose (puerto 8080)."
else
    log "✅ Contenedor 'cadvisor' ya existe."
    # Si el contenedor está parado, lo arrancamos
    if [[ "$(docker inspect -f '{{.State.Status}}' cadvisor)" != "running" ]]; then
        docker start cadvisor
        log "✅ Contenedor 'cadvisor' iniciado."
    fi
fi

# ---------- 8️⃣  CONFIGURAR FIREWALL (si ufw está presente) ----------
if command -v ufw >/dev/null 2>&1; then
    log "🛡️ Configurando ufw (puertos 9100 y 8080)…"
    ufw allow 9100/tcp
    ufw allow 8080/tcp
    ufw reload
    log "✅ Reglas de firewall aplicadas."
else
    log "⚠️ ufw no está instalado → se omite la configuración de firewall."
fi

# ---------- 9️⃣  RESUMEN FINAL ----------
cat <<EOF

✅  ${GREEN}Instalación completada${NC}
---------------------------------------------
📦 Node Exporter  →  http://<IP_VPS>:9100/metrics
📦 cAdvisor       →  http://<IP_VPS>:8080/metrics
🚀 Docker daemon   →  $(systemctl is-active docker)

💡  Próximos pasos
   1️⃣  Añade este VPS desde la UI de Aigents Pulse → "Nucleus Config".
   2️⃣  Verifica que ambos endpoints devuelvan métricas:
        curl -s http://localhost:9100/metrics | head -n 5
        curl -s http://localhost:8080/metrics | head -n 5
   3️⃣  Configura tu archivo .env con FERNET_KEY y credenciales SMTP.

👨‍💻  Si encuentras errores, revisa:
   • systemctl status docker
   • journalctl -u docker -n 30
   • docker logs cadvisor

---  
Desarrollado por Ing. Ángel David Yaguana | Aigents Solutions
EOF
