# Manual de Persistencia Total: Aigents Pulse v3.1 (Spectre+)

Este manual garantiza que tanto la aplicación principal (Master) como los agentes de monitoreo en los VPS clientes se mantengan activos permanentemente, incluso después de un reinicio del servidor o fallos del proceso.

---

## 1. Persistencia del Servidor Maestro (Aplicación Pulse)

Para evitar que la aplicación se detenga al cerrar la terminal, se debe configurar como un servicio de **systemd**.

### Pasos:
1. Navega al directorio del proyecto en el servidor maestro.
2. Ejecuta el script de configuración automática:
   ```bash
   sudo bash setup_master_service.sh
   ```
3. Verifica el estado:
   ```bash
   systemctl status aigents-pulse
   ```

Este servicio cargará automáticamente el entorno virtual (`.venv`), iniciará Streamlit y activará el daemon de monitoreo de fondo en cada arranque.

---

## 2. Persistencia de los Agentes (VPS Monitorizados)

Los agentes de monitoreo (Node Exporter y cAdvisor) y las herramientas de seguridad (Fail2Ban, Auditd) ya están diseñados para ser persistentes si se usaron los instaladores oficiales.

### Verificación en cada VPS Agente:

#### A. Node Exporter (Métricas del Sistema)
El instalador crea un servicio systemd llamado `node_exporter`.
```bash
sudo systemctl enable --now node_exporter
sudo systemctl status node_exporter
```

#### B. cAdvisor (Métricas de Docker)
Se ejecuta como un contenedor Docker con la política `--restart=always`. Esto garantiza que Docker lo inicie automáticamente al arrancar el motor.
```bash
sudo docker update --restart=always cadvisor
sudo docker ps | grep cadvisor
```

#### C. Herramientas de Seguridad
El script `install_security.sh` habilita estos servicios para que arranquen con el sistema:
```bash
sudo systemctl enable fail2ban
sudo systemctl enable auditd
sudo systemctl enable ufw
```

---

## 3. Resumen de Comandos de Control

### Servidor Maestro:
- **Reiniciar App:** `sudo systemctl restart aigents-pulse`
- **Ver Logs en vivo:** `journalctl -u aigents-pulse -f`
- **Detener:** `sudo systemctl stop aigents-pulse`

### VPS Agentes:
- **Verificar Firewall:** `sudo ufw status`
- **Verificar Docker:** `sudo docker ps`
- **Logs de Node Exporter:** `journalctl -u node_exporter -f`

---
**Desarrollado por:** Ing. Ángel David Yaguana | Aigents Solutions  
**Estado del Sistema:** Alta Disponibilidad Operativa
