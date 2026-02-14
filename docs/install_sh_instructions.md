**`install.sh` – Instalador automatizado de agentes (Node Exporter + cAdvisor)**  

```bash
#!/usr/bin/env bash
# =============================================================================
# Aigents Pulse v3.1 (Spectre+)
# Instalador automático de agentes para cada VPS cliente:
#   • Docker Engine (requerido por cAdvisor)
#   • Node Exporter  (puerto 9100/tcp)
#   • cAdvisor      (puerto 8080/tcp)
# =============================================================================
# IMPORTANTE:
#   * El script **debe ejecutarse con privilegios de super‑usuario**.
#   * Si se lanza sin root abortará con el mensaje “run as root”.
# =============================================================================

set -euo pipefail                               # Fail fast, no undefined vars

# -------------------------------------------------------------------------
# Colores para la salida
# -------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'   # No Color

APP_NAME="Aigents Pulse Installer"

log_info() { echo -e "${YELLOW}[${APP_NAME}]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[${APP_NAME}]${NC} $*"; }
log_err()  { echo -e "${RED}[${APP_NAME} ERROR]${NC} $*"; }

# -------------------------------------------------------------------------
# 0️⃣  Verificar que se está ejecutando como root
# -------------------------------------------------------------------------
if [[ "$EUID" -ne 0 ]]; then
    log_err "Este script necesita privilegios de root."
    log_err "Ejemplo: sudo $0   o   su -c \"$0\""
    exit 1
fi

# -------------------------------------------------------------------------
# 1️⃣  Funciones auxiliares
# -------------------------------------------------------------------------
command_exists() { command -v "$1" >/dev/null 2>&1; }

# -------------------------------------------------
# Docker Engine ---------------------------------------------------------
install_docker() {
    log_info "🔧 Instalando Docker Engine..."

    # Si el paquete docker‑ce no está disponible, añadimos el repo oficial
    if ! apt-get -qq list docker-ce >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y ca-certificates curl gnupg lsb-release

        mkdir -p /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
          | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

        # Detectar codename (fallback a "focal" si lsb_release falta)
        DISTRO_CODENAME=$(lsb_release -cs 2>/dev/null || echo "focal")
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
          https://download.docker.com/linux/ubuntu ${DISTRO_CODENAME} stable" \
          > /etc/apt/sources.list.d/docker.list

        apt-get update -y
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    else
        log_info "Docker ya está disponible en los repositorios."
    fi

    # Habilitar e iniciar el daemon
    systemctl enable --now docker
    if systemctl is-active --quiet docker; then
        log_ok "Docker daemon está activo."
    else
        log_err "No se pudo iniciar Docker. Revisa los logs con:"
        log_err "  journalctl -u docker -n 30"
        exit 1
    fi

    # Prueba rápida
    log_info "✅ Ejecutando prueba rápida de Docker..."
    if docker run --rm hello-world >/dev/null 2>&1; then
        log_ok "Docker funciona correctamente."
    else
        log_err "La prueba Docker falló. Verifica que el socket exista y que tu usuario tenga permisos."
        exit 1
    fi
}
# -------------------------------------------------
# Node Exporter ---------------------------------------------------------
install_node_exporter() {
    local version="1.7.0"
    local bin_path="/usr/local/bin/node_exporter"

    if [[ -x "$bin_path" ]]; then
        log_ok "Node Exporter ya está instalado en $bin_path."
        return
    fi

    log_info "📊 Instalando Node Exporter v${version}..."
    cd /tmp
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v${version}/node_exporter-${version}.linux-amd64.tar.gz"
    tar xzf "node_exporter-${version}.linux-amd64.tar.gz"
    cp "node_exporter-${version}.linux-amd64/node_exporter" "$bin_path"
    chmod +x "$bin_path"

    # Usuario sin login para mayor seguridad
    id -u node_exporter >/dev/null 2>&1 || useradd -rs /bin/false node_exporter

    # Systemd service
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

    if systemctl is-active --quiet node_exporter; then
        log_ok "Node Exporter activo (puerto 9100)."
    else
        log_err "Node Exporter no pudo iniciarse."
        exit 1
    fi
}
# -------------------------------------------------
# cAdvisor ---------------------------------------------------------------
install_cadvisor() {
    # Si el contenedor ya existe, lo reutilizamos
    if docker ps -a --format '{{.Names}}' | grep -q '^cadvisor$'; then
        if [[ "$(docker inspect -f '{{.State.Status}}' cadvisor)" != "running" ]]; then
            log_info "⏩ Arrancando contenedor cAdvisor existente..."
            docker start cadvisor
        else
            log_ok "cAdvisor ya está corriendo."
        fi
        return
    fi

    log_info "🐳 Desplegando cAdvisor (Docker)…"
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

    # Esperar brevemente para que el contenedor arranque
    sleep 5
    if [[ "$(docker inspect -f '{{.State.Status}}' cadvisor)" == "running" ]]; then
        log_ok "cAdvisor está en ejecución (puerto 8080)."
    else
        log_err "cAdvisor no pudo iniciarse. Revisa con: docker logs cadvisor"
        exit 1
    fi
}
# -------------------------------------------------
# Firewall (ufw) ---------------------------------------------------------
configure_firewall() {
    if command_exists ufw; then
        log_info "🛡️ Configurando ufw (puertos 9100/tcp y 8080/tcp)…"
        ufw allow 9100/tcp
        ufw allow 8080/tcp
        ufw reload
        log_ok "Reglas ufw aplicadas."
    else
        log_info "ufw no está instalado. Saltando configuración del firewall."
    fi
}
# -------------------------------------------------
# Resumen final -----------------------------------------------------------
print_summary() {
    cat <<EOF

${GREEN}✅ Instalación completada${NC}
--------------------------------------------
📦 Node Exporter  → http://<IP_VPS>:9100/metrics
📦 cAdvisor       → http://<IP_VPS>:8080/metrics
🚀 Docker daemon  → $(systemctl is-active docker)

💡 Próximos pasos
   1️⃣ Añade este VPS desde la UI de Aigents Pulse → **Nucleus Config** → **Add new VPS**.
   2️⃣ Verifica los endpoints:
        curl -s http://localhost:9100/metrics | head -n 5
        curl -s http://localhost:8080/metrics | head -n 5
   3️⃣ Asegúrate de que cualquier firewall entre el servidor central y este VPS permite los puertos 9100 y 8080.

---  
Desarrollado por Ing. Ángel David Yaguana, Dr. h.c. – CAIO & CIO | Aigents Solutions
EOF
}
# -------------------------------------------------------------------------
# 2️⃣  Ejecución del instalador
# -------------------------------------------------------------------------
log_info "🚀 Iniciando instalador de agentes Aigents Pulse…"

install_docker
install_node_exporter
install_cadvisor
configure_firewall
print_summary
```

### Cómo usarlo  

```bash
# 1️⃣ Copia el script al VPS cliente
scp install.sh user@<IP_VPS>:/tmp/

# 2️⃣ Conéctate al VPS
ssh user@<IP_VPS>

# 3️⃣ Ejecuta como root (obligatorio)
sudo bash /tmp/install.sh
```

El script se detendrá inmediatamente si no se ejecuta con privilegios de super‑usuario, evitando el error habitual de Docker *“failed to connect to the docker API … no such file or directory”*.  

Una vez finalizado, verifica los endpoints con `curl -s http://localhost:9100/metrics` y `curl -s http://localhost:8080/metrics`, y regístralo en la UI de **Aigents Pulse**.  