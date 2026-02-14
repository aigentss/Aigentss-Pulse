# Manual de Despliegue - Aigents Pulse v3.1 (Spectre+)

**Desarrollado por:** Ing. Ángel David Yaguana, Dr. h.c.  
**Fecha:** 2026-02-14  
**Propiedad Intelectual:** Aigents Solutions Corp (USA) / SAS (Ecuador)

---

Este manual detalla paso a paso cómo desplegar la plataforma **Aigents Pulse v3.1 (Spectre+)** desde cero. Se cubre tanto la instalación del **Servidor Central (Monitor)** como la configuración de los **Agentes remotos (VPS)**.

## 📋 Prerrequisitos

- **Servidor Central:** Ubuntu 20.04/22.04 LTS o Debian 11/12. Python 3.12 instalado. Acceso root.
- **VPS Clientes:** Cualquier distro Linux compatible con Docker (Ubuntu, Debian, CentOS, AlmaLinux).
- **Acceso a Internet:** Para descargar paquetes y repositorios.
- **Git:** Instaldo en el servidor central (si se despliega desde código fuente).

---

## 🚀 Fase 1: Despliegue del Servidor Central (Monitor)

El servidor central aloja el Dashboard (Streamlit), la Base de Datos (SQLite) y el Demonio de Monitoreo.

### 1. Clonar el Repositorio

Accede a tu servidor vía SSH y clona la rama `Spectre+`:

```bash
cd /opt
sudo git clone -b Spectre+ https://github.com/sherckuith/Aigentss-Pulse.git
cd Aigentss-Pulse
```

### 2. Configurar el Entorno Python

```bash
# Instalar venv si no existe
sudo apt update && sudo apt install -y python3.12-venv

# Crear entorno virtual
python3.12 -m venv .venv

# Activar entorno
source .venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuración de Seguridad

Genera la clave maestra de encriptación y configura el archivo `.env`.

```bash
# Generar clave Fernet
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Crea el archivo `.env`:

```bash
nano .env
```

Contenido:
```ini
FERNET_KEY=PEGAR_TU_CLAVE_AQUI
# SMTP Config (Encriptado)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER_ENC=...
SMTP_PASS_ENC=...
ALERT_EMAIL=admin@aigents.com
```

### 4. Configurar el Servicio (Systemd)

Para que Aigents Pulse se inicie automáticamente con el servidor:

```bash
# Ejecutar script de configuración de servicio
sudo bash scripts/setup_master_service.sh
```

Verificar estado:
```bash
sudo systemctl status aigents-pulse
```

---

## 📡 Fase 2: Instalación de Agentes en VPS Clientes

En cada VPS que desees monitorizar, debes instalar los agentes (Node Exporter + cAdvisor).

### Opción A: Instalación Automática (Recomendada)

Desde el **Servidor Central**, copia el instalador al VPS destino:

```bash
# Reemplaza IP_DESTINO con la IP del VPS cliente
scp scripts/install.sh root@IP_DESTINO:/tmp/
```

Accede al VPS y ejecuta:

```bash
ssh root@IP_DESTINO
bash /tmp/install.sh
```

El script se encargará de:
1. Instalar Docker.
2. Levantar Node Exporter y cAdvisor.
3. Abrir puertos 9100/8080 en UFW.

### Opción B: Instalación Manual

Si el script falla, ejecuta manualmente en el VPS:

```bash
# 1. Node Exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
tar xvfz node_exporter-*.*
cd node_exporter-*.*
./node_exporter &

# 2. cAdvisor (Docker)
docker run -d --name=cadvisor --privileged \
  -p 8080:8080 \
  -v /:/rootfs:ro \
  -v /var/run:/var/run:ro \
  -v /sys:/sys:ro \
  -v /var/lib/docker/:/var/lib/docker:ro \
  -v /dev/disk/:/dev/disk:ro \
  gcr.io/cadvisor/cadvisor:v0.47.0
```

---

## 🖥️ Fase 3: Acceso y Operación

### Acceder al Dashboard

Abre tu navegador y ve a:
`http://IP_SERVIDOR_CENTRAL:8501`

### Agregar VPS al Monitor

1. Ve a la pestaña **"Nucleus Config"**.
2. Ingresa la IP del nuevo VPS.
3. Dale un nombre (ej: `Web-Server-01`).
4. Guarda y activa el check "Enabled".

El sistema comenzará a recibir datos en 60 segundos.

---

## 🛠️ Mantenimiento

### Actualizar la Aplicación

```bash
cd /opt/Aigentss-Pulse
git pull origin Spectre+
bash scripts/restart_and_clear.sh
```

### Limpieza de Base de Datos (Auto-Healing)

El sistema se auto-repara, pero si necesitas forzar una limpieza:

```bash
source .venv/bin/activate
python3 db_cleanup_metrics.py
```

---

**Soporte Técnico:**  
Contactar a **Ing. Ángel David Yaguana**  
Aigents Solutions Corp.
