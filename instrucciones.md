# instrucciones.md – Guía paso a paso para instalar agentes en los VPS clientes  

---  

## 📑  Índice  

1. [Requisitos previos](#11‑requisitos-previos)  
2. [Ejecución del instalador automático (recomendado)](#2‑ejecución‑del‑instalador‑automático-recomendado)  
3. [Instalación manual (alternativa sin script)](#3‑instalación‑manual-alternativa-sin‑script)  
4. [Auditoría de Seguridad (Security Dashboard)](#paso-4-auditoría-de-seguridad-security-dashboard)
5. [Verificación Final](#paso-5-verificación-final)
6. [Registro del VPS en la UI de Aigents Pulse](#5‑registro‑del‑vps‑en‑la‑ui-de‑aigents‑pulse)  
7. [Solución de problemas comunes](#6‑solución‑de-problemas-comunes)  
8. [Próximos pasos en el servidor central](#7‑próximos‑pasos-en‑el‑servidor‑central)  

---  

## 1️⃣  Requisitos previos  

| Requisito | Detalle |
|-----------|---------|
| **Sistema operativo** | Ubuntu 20.04 LTS / 22.04 LTS, Debian 11/12 (otros pueden requerir ajustes). |
| **Acceso root / sudo** | **Obligatorio** para instalar paquetes, crear servicios systemd y abrir puertos. Si el script se ejecuta sin estos privilegios abortará con el mensaje *“run as root”*. |
| **Conexión a Internet** | Necesario para descargar paquetes, contenedores Docker y binarios. |
| **Puertos** | 9100 /tcp (Node Exporter) y 8080 /tcp (cAdvisor) deben quedar accesibles desde el servidor central. |
| **Herramientas básicas** | `scp`, `ssh`, `curl`, `wget`, `systemctl`, `docker`. Todas vienen por defecto en Ubuntu/Debian. |

---  

## 2️⃣  Ejecución del instalador automático (recomendado)  

### 2.1  Copiar el script al VPS  

```bash
# Desde tu máquina de administración (no el VPS)
scp install.sh usuario@<IP_VPS>:/tmp/
```

### 2.2  Conectarse al VPS  

```bash
ssh usuario@<IP_VPS>
```

### 2.3  Ejecutar con privilegios de super‑usuario  

```bash
# Dar permisos de ejecución (opcional)
sudo chmod +x /tmp/install.sh

# **Ejecútalo con sudo** (o como root)
sudo /tmp/install.sh
```

> **⚠️ Si lo lanzas sin `sudo` el script imprimirá:**  
> ```
> ⚠️  ERROR: Este script necesita privilegios de root.
> Ejecuta: sudo ./install.sh   o   cambia a la cuenta root antes de iniciar.
> ```  
> y terminará sin instalar nada, lo que provoca el clásico error *“failed to connect to the docker API … no such file or directory”*.

### 2.4  Qué hace el script (resumen)  

1. Actualiza la lista de paquetes del sistema.  
2. Instala Docker Engine (si no existe) y asegura que el daemon está **activo**.  
3. Ejecuta una prueba `docker run hello-world`.  
4. Instala **Node Exporter** (puerto 9100) como servicio systemd.  
5. Despliega **cAdvisor** en Docker (puerto 8080).  
6. (Opcional) abre los puertos 9100 y 8080 mediante **ufw**.  
7. Muestra un resumen con los endpoints y los pasos siguientes.

---  

## 3️⃣  Instalación manual (alternativa sin script)  

> Usa esta sección solo si el script no está disponible o prefieres paso a paso.

### 3.1  Instalar Docker Engine  

```bash
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release

sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Habilitar e iniciar el daemon
sudo systemctl enable --now docker
```

#### Verificar  

```bash
sudo systemctl status docker          # debe estar active (running)
ls -l /var/run/docker.sock            # debe existir
docker run --rm hello-world          # debe imprimir “Hello from Docker!”
```

### 3.2  Instalar Node Exporter  

```bash
VERSION="1.7.0"
cd /tmp
wget -q https://github.com/prometheus/node_exporter/releases/download/v${VERSION}/node_exporter-${VERSION}.linux-amd64.tar.gz
tar xzf node_exporter-${VERSION}.linux-amd64.tar.gz
sudo cp node_exporter-${VERSION}.linux-amd64/node_exporter /usr/local/bin/
sudo chmod +x /usr/local/bin/node_exporter
sudo useradd -rs /bin/false node_exporter || true

# Crear service systemd
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

sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
```

#### Verificar  

```bash
curl -s http://localhost:9100/metrics | head -n 5
```

### 3.3  Desplegar cAdvisor (Docker)

```bash
sudo docker pull gcr.io/cadvisor/cadvisor:latest

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
```

#### Verificar  

```bash
sudo docker ps --filter name=cadvisor          # debe estar “Up”
curl -s http://localhost:8080/metrics | head -n 5
```

### 3.4  Abrir puertos en el firewall (si usas ufw)

```bash
if command -v ufw >/dev/null 2>&1; then
    sudo ufw allow 9100/tcp
    sudo ufw allow 8080/tcp
    sudo ufw reload
fi
```

---

## PASO 4: Auditoría de Seguridad (Security Dashboard)

Para activar el panel de seguridad avanzado, ejecute el instalador de seguridad:

1. **Ejecutar el script de seguridad:**
   ```bash
   sudo bash install_security.sh
   ```

2. **Beneficios del Security Dashboard:**
   - Auditoría de puertos abiertos.
   - Monitoreo de throughput por puerto.
   - Verificación de hardening SSH.
   - Estado de Fail2Ban y Firewall (UFW).

---

## PASO 5: Verificación Final

Ejecuta **todos** los siguientes comandos desde el VPS. Cada uno debe devolver salida **sin errores**.

| Comando | Qué comprueba |
|---------|----------------|
| `systemctl status docker` | El daemon está activo. |
| `docker ps -a | grep cadvisor` | El contenedor cAdvisor está creado y en **Up**. |
| `curl -s http://localhost:9100/metrics | head -n 5` | Node Exporter responde con métricas del kernel. |
| `curl -s http://localhost:8080/metrics | head -n 5` | cAdvisor responde con métricas de contenedores. |
| `docker run --rm hello-world` | Docker funciona correctamente. |

Si alguno falla, revisa la sección **6️⃣ Solución de problemas**.

---  

## 5️⃣  Registro del VPS en la UI de Aigents Pulse  

1. Abre la UI del servidor central (por defecto `http://<IP_SERVIDOR>:8501`).  
2. Navega a **Nucleus Config** → **➕ Añadir nuevo VPS**.  
3. Completa:  

   - **IP Address** → dirección del VPS que acabas de preparar.  
   - **Friendly Name** → nombre descriptivo (p.ej. `web‑prod‑01`).  
   - **Node Exporter Port** → `9100`.  
   - **cAdvisor Port** → `8080`.  

4. Marca **Active** y pulsa **Save VPS Node**.  

> El *daemon* de monitorización (MonitorDaemon) comenzará a scrappear métricas en el intervalo configurado (predeterminado 60 s).  

---  

## 6️⃣  Solución de problemas comunes  

| Síntoma | Posible causa | Pasos de diagnóstico / solución |
|---------|----------------|--------------------------------|
| **`failed to connect to the docker API … no such file or directory`** | Docker daemon no está corriendo o falta el socket. | ```bash sudo systemctl status docker``` → si está “inactive”, arráncalo: `sudo systemctl start docker`. Verifica el socket: `ls -l /var/run/docker.sock`. |
| **`permission denied` al ejecutar `docker run …`** | El usuario actual no pertenece al grupo `docker`. | ```bash sudo usermod -aG docker $USER``` → cierra sesión y vuelve a entrar (o `newgrp docker`). |
| **Node Exporter no responde** | Service detenido o firewall bloqueado. | ```bash sudo systemctl status node_exporter``` → `sudo systemctl restart node_exporter`. Verifica ufw: `sudo ufw status | grep 9100`. |
| **cAdvisor devuelve 404 o está “Exited”** | Contenedor caído o puerto no expuesto. | ```bash sudo docker logs cadvisor``` → busca errores. Reinicia: `sudo docker start cadvisor`. |
| **Los puertos 9100/8080 no son accesibles desde el servidor central** | Firewall local o de red bloqueando. | ```bash sudo ufw status``` → si está activo, asegúrate de haber permitido los puertos. En entornos cloud verifica grupos de seguridad (AWS SG, Azure NSG, etc.). |
| **Los comandos `curl …/metrics` devuelven HTML vacío** | El proceso no está escuchando en el puerto esperado. | Verifica con `netstat -tnlp | grep 9100` y `netstat -tnlp | grep 8080`. Si no aparecen, revisa los logs del service correspondiente. |

---  

## 7️⃣  Próximos pasos en el servidor central  

1. **Generar la clave Fernet** (solo una vez, en el servidor central):  

   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```  

   Copia el valor en el archivo `.env` del servidor:  

   ```ini
   FERNET_KEY=TU_CLAVE_GENERADA_AQUI
   ```

2. **Configurar credenciales SMTP** (en `.env` o mediante la UI).  
3. **Iniciar la aplicación** (si no está corriendo):  

   ```bash
   source .venv/bin/activate        # si usas virtualenv
   streamlit run app.py --server.port 8501 --server.address 0.0.0.0
   ```

4. **Comprobar que los datos llegan**:  

   - En la pestaña **Status Live** deberías ver los VPS recién añadidos con métricas en tiempo real.  
   - En **History & Export** revisa que la tabla de historial se llena.  

5. (Opcional) **Programar reportes** y habilitar alertas a través de la UI → **Alerts**.  

---  

**Desarrollado por**  
Ing. **Ángel David Yaguana**, Dr. h.c. – CAIO & CIO | **Aigents Solutions**  
**Versión:** **3.1.0 (Spectre+)** – 10 feb 2026  

---  