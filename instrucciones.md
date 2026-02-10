# Guía de Instalación de Agentes de Monitoreo

Esta guía detalla los pasos para configurar un VPS Linux (Ubuntu/Debian) para ser monitoreado por **Aigentss Pulse**.
Necesitamos instalar dos componentes:
1. **Node Exporter**: Para métricas del sistema (CPU, RAM, Disco) - Puerto `9100`.
2. **cAdvisor**: Para métricas de contenedores Docker - Puerto `8080`.

---

## 1. Preparación del Sistema 🛠️

Accede a tu VPS vía SSH y actualiza los repositorios:
```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Instalación de Node Exporter (Sistema) 🖥️

Node Exporter recorre el kernel de Linux y expone métricas en el puerto 9100.

### Paso 2.1: Crear usuario y descargar
```bash
# Crear usuario de sistema sin acceso a shell
sudo useradd --no-create-home --shell /bin/false node_exporter

# Descargar la última versión (Verificar versión actual en prometheus.io)
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz

# Descomprimir y mover el binario
tar xvf node_exporter-1.7.0.linux-amd64.tar.gz
sudo cp node_exporter-1.7.0.linux-amd64/node_exporter /usr/local/bin/
sudo chown node_exporter:node_exporter /usr/local/bin/node_exporter

# Limpiar archivos descargados
rm -rf node_exporter-1.7.0.linux-amd64.tar.gz node_exporter-1.7.0.linux-amd64
```

### Paso 2.2: Crear el servicio Systemd
Crea el archivo de servicio:
```bash
sudo nano /etc/systemd/system/node_exporter.service
```

Pega el siguiente contenido:
```ini
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
```

### Paso 2.3: Iniciar el servicio
```bash
sudo systemctl daemon-reload
sudo systemctl start node_exporter
sudo systemctl enable node_exporter
```

Verifica que esté corriendo:
```bash
sudo systemctl status node_exporter
# Deberías ver "Active: active (running)"
```

---

## 3. Instalación de cAdvisor (Docker Metrics) 🐳

cAdvisor (Container Advisor) de Google es el estándar para extraer métricas de uso de recursos de contenedores en ejecución.

### Prerrequisitos
Tener Docker instalado.

### Paso 3.1: Ejecutar el contenedor de cAdvisor
Ejecuta el siguiente comando para levantar cAdvisor en el puerto `8080`:

```bash
sudo docker run \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --volume=/dev/disk/:/dev/disk:ro \
  --publish=8080:8080 \
  --detach=true \
  --name=cadvisor \
  --restart=always \
  --privileged \
  --device=/dev/kmsg \
  gcr.io/cadvisor/cadvisor:latest
```

*(Nota: En algunas versiones de ARM64/Raspberry Pi, la imagen puede variar a `gcr.io/cadvisor/cadvisor-arm64`).*

---

## 4. Configuración del Firewall (Seguridad) 🛡️

Es **CRÍTICO** permitir el tráfico en los puertos `9100` y `8080` **SOLO** desde la IP del servidor de monitoreo (Aigentss Pulse) para evitar exponer métricas sensibles a todo internet.

Si usas `ufw`:
```bash
# Reemplaza MONITOREO_IP con la IP donde corre Aigentss Pulse
sudo ufw allow from <MONITOREO_IP> to any port 9100 proto tcp
sudo ufw allow from <MONITOREO_IP> to any port 8080 proto tcp
sudo ufw reload
```

---

## 5. Verificación ✅

Desde tu navegador o desde el servidor de monitoreo:
1. **Node Exporter**: `http://<VPS_IP>:9100/metrics`
2. **cAdvisor**: `http://<VPS_IP>:8080/metrics`

Si ves un muro de texto con datos como `node_cpu_seconds_total` o `container_memory_usage_bytes`, ¡estás listo!
