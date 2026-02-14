#!/bin/bash
# ==============================================================================
# Aigents Pulse v3.1 (Spectre+)
# Developed by: Ing. Ángel David Yaguana, Dr. h.c.
# Date: 2026-02-14
# Propietario: Ing. Ángel David Yaguana, Dr. h.c.
#
# Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
# Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
# PROPRIETARY AND CONFIDENTIAL.
#
# Security Module Installer.
Installs fail2ban and configures basic security auditing tools.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

if [[ "$EUID" -ne 0 ]]; then
    echo -e "${RED}ERROR:${NC} Necesita ejecutarse con privilegios de root (sudo)."
    exit 1
fi

echo -e "${GREEN}🔧 Instalando paquetes de seguridad y auditoría...${NC}"

# Detectar gestor de paquetes (Ubuntu/Debian)
apt-get update -y
apt-get install -y nmap net-tools ufw fail2ban auditd apparmor-utils

# -------------------------------------------------
# 1. Configuración de Firewall (UFW)
# -------------------------------------------------
echo -e "${YELLOW}🛡️ Configurando UFW (Uncomplicated Firewall)...${NC}"
if ufw status | grep -iq inactive; then
    ufw default deny incoming
    ufw default allow outgoing
    # Asegurar puertos críticos de Aigents Pulse
    ufw allow 22/tcp      # SSH
    ufw allow 9100/tcp    # Node Exporter
    ufw allow 8080/tcp    # cAdvisor
    ufw allow 8501/tcp    # Streamlit (si es el master)
    echo "y" | ufw enable
fi

# -------------------------------------------------
# 2. Configuración de Fail2Ban
# -------------------------------------------------
echo -e "${YELLOW}🚫 Configurando Fail2Ban para SSH...${NC}"
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port    = ssh
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600
EOF
systemctl restart fail2ban
systemctl enable fail2ban

# -------------------------------------------------
# 3. Activación de Auditd
# -------------------------------------------------
echo -e "${YELLOW}📝 Activando auditoría del sistema (auditd)...${NC}"
systemctl enable --now auditd

# -------------------------------------------------
# 4. Verificación de AppArmor
# -------------------------------------------------
if systemctl is-enabled apparmor >/dev/null 2>&1; then
    echo -e "${GREEN}✅ AppArmor está habilitado.${NC}"
else
    echo -e "${YELLOW}⚠️ AppArmor no está habilitado, activando...${NC}"
    systemctl enable --now apparmor || true
fi

echo -e "${GREEN}✅ Instalación de seguridad completada con éxito.${NC}"
echo "------------------------------------------------"
echo "CONSEJOS ADICIONALES:"
echo "1. Deshabilita el acceso root por SSH: PermitRootLogin no"
echo "2. Usa llaves SSH en lugar de contraseñas: PasswordAuthentication no"
echo "3. Revisa los logs de seguridad en: /var/log/auth.log"
echo "------------------------------------------------"
echo "Desarrollado por: Ing. Ángel David Yaguana | Aigents Solutions"
