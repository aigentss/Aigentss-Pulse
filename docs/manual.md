# Manual de Administración y Despliegue – Aigents Pulse v3.1 (Spectre+)

Este documento describe, paso a paso, todo lo necesario para **preparar cada VPS cliente** que será monitorizado por la plataforma **Aigents Pulse**.  
Incluye la instalación de Docker, Node Exporter, cAdvisor, la apertura de puertos y la generación de la clave Fernet para el servidor central.

> **⚠️ IMPORTANTE**  
> El instalador `install.sh` y los comandos que alteran el sistema (instalación de paquetes, creación de servicios, apertura de puertos, despliegue de contenedores) **requieren privilegios de super‑usuario**.  
> Ejecuta siempre los bloques con `sudo` o conviértete en `root` antes de iniciar.  
> Si intentas correr el script sin estos privilegios, abortará mostrando el mensaje *“run as root”* y no se instalará nada, lo que lleva al error típico:  
> `failed to connect to the docker API … no such file or directory`.

---

## 📦 0️⃣  Prerrequisitos generales

| Requisito                              | Comentario                                                                      |
|----------------------------------------|---------------------------------------------------------------------------------|
| Sistema operativo                      | Ubuntu 20.04 LTS / 22.04 LTS o Debian 11/12 (otros pueden funcionar con ajustes) |
| Acceso **root** o **sudo**              | Necesario para instalar paquetes, crear servicios y montar volúmenes Docker.     |
| Conexión a internet desde el VPS       | Para descargar binarios y contenedores.                                         |
| Puertos **9100** (Node Exporter) y **8080** (cAdvisor) deben estar accesibles desde el servidor central. |

---

## 🏗️ 1️⃣  Instalación de Docker y Docker Compose *(requerido para cAdvisor)*

```bash
# -------------------------------------------------
# 1.1  Actualizar índices de paquetes
sudo apt-get update -y

# 1.2  Instalar paquetes de soporte
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 1.3  Añadir la clave GPG oficial de Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
 | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 1.4  Añadir el repositorio de Docker (Ubuntu/Debian)
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
 | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 1.5  Actualizar índices con el nuevo repositorio
sudo apt-get update -y

# 1.6  Instalar Docker Engine y Docker Compose plugin
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 1.7  Habilitar e iniciar el daemon de Docker
sudo systemctl enable --now docker
# -------------------------------------------------
```

### 1.8  Verificar que el daemon está activo

```bash
# El servicio debe estar “active (running)”
sudo systemctl status docker

# El socket de Docker debe existir
ls -l /var/run/docker.sock
```

Si el servicio no está activo, arráncalo manualmente:

```bash
sudo systemctl start docker
```

### 1.9  Prueba rápida de Docker

```bash
docker run --rm hello-world
```

Deberías ver el mensaje *“Hello from Docker!”*. Si falla, revisa los logs:

```bash
journalctl -u docker -n 30
```

---

## 📊 2️⃣  Instalación de **Node Exporter** (métricas del sistema)

> **Node Exporter** escucha en el puerto **9100/tcp** y expone métricas en formato Prometheus.

```bash
# -------------------------------------------------
# 2.1  Variables
VERSION="1.7.0"
BIN_PATH="/usr/local/bin/node_exporter"

# 2.2  Descargar y descomprimir
cd /tmp
wget -q https://github.com/prometheus/node_exporter/releases/download/v${VERSION}/node_exporter-${VERSION}.linux-amd64.tar.gz
tar xzf node_exporter-${VERSION}.linux-amd64.tar.gz

# 2.3  Copiar binario al PATH
sudo cp node_exporter-${VERSION}.linux-amd64/node_exporter "$BIN_PATH"
sudo chmod +x "$BIN_PATH"

# 2.4  Crear usuario sin login para mayor seguridad
sudo useradd -rs /bin/false node_exporter || true

# 2.5  Definir el service de systemd
sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<'EOF'
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

# 2.6  Recargar systemd y habilitar el servicio
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
# -------------------------------------------------
```

### 2.7  Verificar que funciona

```bash
curl -s http://localhost:9100/metrics | head -n 10
```

Deberías ver líneas con `node_cpu_seconds_total`, `node_memory_MemTotal_bytes`, etc.

---

## 🐳 3️⃣  Despliegue de **cAdvisor** (métricas de Docker)

> **cAdvisor** se ejecuta como contenedor Docker y expone métricas en el puerto **8080/tcp**.

```bash
# -------------------------------------------------
# 3.1  Descargar la última imagen de cAdvisor
sudo docker pull gcr.io/cadvisor/cadvisor:latest

# 3.2  Ejecutar el contenedor (detached)
sudo docker run -d \
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
# -------------------------------------------------
```

### 3.3  Verificar que cAdvisor está activo

```bash
# Listar contenedores y comprobar que está “Up”
sudo docker ps --filter name=cadvisor

# Probar el endpoint
curl -s http://localhost:8080/metrics | head -n 10
```

Si recibes un listado de métricas (`container_cpu_usage_seconds_total`, …) todo está bien.  
En caso de que el contenedor no arranque, revisa los logs:

```bash
sudo docker logs cadvisor
```

---

## 🔐 4️⃣  Instalación de Seguridad (Recomendado)

Para habilitar las funciones del **Security Dashboard**, ejecuta el script de seguridad en cada nodo VPS:

```bash
sudo bash install_security.sh
```

Este script automatiza:
- **Firewall (UFW):** Activa el firewall y permite solo puertos SSH, Node Exporter y cAdvisor.
- **Fail2Ban:** Configura protecciones contra fuerza bruta en SSH.
- **Auditd:** Inicia el daemon de auditoría de eventos del sistema.
- **Nmap:** Instalación de herramientas para el motor de escaneo de Aigents Pulse.

---

## 🛰️ 5️⃣  Security Dashboard v3.1 (Spectre+)

El Dashboard de Seguridad proporciona una auditoría en tiempo real de la postura de seguridad de cada nodo.

### Funcionalidades:
- **Estado del Firewall:** Monitoreo del estado dinámico de UFW (Active/Inactive).
- **Protección F2B:** Verificación de que Fail2Ban esté protegiendo activamente.
- **Auditoría de Puertos:** Escaneo remoto/local de puertos críticos (22, 80, 443, 3306, etc.).
- **Tráfico por Puerto:** Gráficos de Rx/Tx (KB/s) por cada puerto activo para detectar posibles fugas de datos o ataques.

### Alertas de Seguridad:
Pulse v3.1 detecta cambios en la configuración de seguridad (hash-based change detection) y envía alertas automáticas si se modifican las políticas de firewall o se abren puertos sospechosos.

---

## 🔐 6️⃣  Generación de la clave FERNET
 (para el servidor central)

Aigents Pulse cifra en base de datos las credenciales SMTP con **Fernet**.  
Esto solo se requiere en el **servidor central**, pero el agente necesita que la variable de entorno exista para poder enviar datos cifrados (aunque normalmente no se usa allí).

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copia la salida en el archivo `.env` del **servidor central**:

```ini
FERNET_KEY=TU_CLAVE_GENERADA_AQUI
```

> **No** es necesario colocar la clave en los VPS clientes a menos que se quiera cifrar datos locales.  

---

## 🧪 6️⃣  Verificación final de los agentes instalados

Ejecuta, **desde el VPS cliente**, los siguientes comandos y asegúrate de obtener salida sin errores:

```bash
# 6.1  Node Exporter (sistema)
curl -s http://localhost:9100/metrics | head -n 5
# → debe devolver varias métricas del kernel

# 6.2  cAdvisor (Docker)
curl -s http://localhost:8080/metrics | head -n 5
# → métricas de contenedores, p.ej. container_cpu_usage_seconds_total

# 6.3  Docker daemon (solo para confirmar)
docker ps -a | head -n 5
# → listado de contenedores (al menos el propio cadvisor)
```

Si cualquiera de los pasos falla:

| Paso | Posible causa | Acción de corrección |
|------|----------------|----------------------|
| **Docker daemon** | No está activo o el socket falta | `sudo systemctl restart docker` → verifica de nuevo. |
| **Node Exporter** | Servicio no iniciado | `sudo systemctl status node_exporter` → `sudo systemctl restart node_exporter`. |
| **cAdvisor** | Contenedor caído | `sudo docker start cadvisor` o revisa logs con `sudo docker logs cadvisor`. |
| **Firewall** | Puertos cerrados | Vuelve a ejecutar el bloque de `ufw` o abre manualmente con iptables. |

---

## 📋 7️⃣  Registro de los VPS en la UI de Aigents Pulse

Una vez que los agentes están funcionando y los puertos son accesibles desde el **servidor central**, registra el nuevo nodo:

1. Accede a la UI (por defecto en `http://<IP_SERVER>:8501`).  
2. Dirígete a **Nucleus Config → ➕ Añadir nuevo VPS**.  
3. Completa los campos:
   - **IP Address** → dirección del VPS cliente.  
   - **Friendly Name** → nombre descriptivo.  
   - **Node Exporter Port** → `9100`.  
   - **cAdvisor Port** → `8080`.  
4. Marca **Active** y guarda.  

El *daemon* de monitoreo empezará a scrappear métricas en el intervalo configurado (por defecto 60 s).  

---

## 🛠️ 8️⃣  Solución de Problemas frecuente

### 8.1 Error: `failed to connect to the docker API … no such file or directory`

- **Causa típica**: El daemon Docker no está corriendo o el socket `/var/run/docker.sock` falta.  
- **Pasos**:
  ```bash
  sudo systemctl status docker
  sudo systemctl start docker
  ls -l /var/run/docker.sock
  ```
- Si el socket está ausente, reinstala Docker (paso 1) y verifica que el paquete `docker-ce` se instaló correctamente.

### 8.2 Error: `permission denied` al ejecutar `docker run …`

- **Causa**: El usuario actual no pertenece al grupo `docker`.  
- **Solución**:
  ```bash
  sudo usermod -aG docker $USER
  newgrp docker   # o cierra sesión y vuelve a entrar
  ```

### 8.3 cAdvisor no muestra métricas (`/metrics` devuelve HTML 404)

- **Causa**: Contenedor detenido o puertos no expuestos correctamente.  
- **Solución**:
  ```bash
  sudo docker ps -a | grep cadvisor
  sudo docker start cadvisor
  sudo docker logs cadvisor   # revisar por errores de permisos
  ```

### 8.4 Node Exporter no responde

- **Causa**: Servicio no habilitado o puerto bloqueado por firewall.  
- **Solución**:
  ```bash
  sudo systemctl status node_exporter
  sudo systemctl restart node_exporter
  sudo ufw status | grep 9100   # debería estar “ALLOW”
  ```

---

## 📚 9️⃣  Referencias rápidas

| Recurso | Enlace |
|---------|--------|
| Repositorio oficial de Docker CE | https://docs.docker.com/engine/install/ubuntu/ |
| Node Exporter – GitHub releases | https://github.com/prometheus/node_exporter/releases |
| cAdvisor – Docker Hub | https://gcr.io/cadvisor/cadvisor |
| Documentación de Aigents Pulse (API, UI) | Dentro del proyecto → `api.py`, `app.py` |
| Guía completa de instalación | `instrucciones.md` (más detalle del paso a paso) |

---

**Desarrollado por:** Ing. **Ángel David Yaguana**, Dr. h.c. – CAIO & CIO | **Aigents Solutions**  
**Versión:** **3.1.0 (Spectre+)** – 10 feb 2026  

---   ```