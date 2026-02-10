# Manual de Uso: Instalador de Seguridades Aigents Pulse v3.1

Este manual describe el proceso para implementar las herramientas de seguridad necesarias en cada VPS cliente. Estas herramientas permiten que el módulo **"Global Security Audit"** de Aigents Pulse funcione correctamente, proporcionando visibilidad sobre el estado del firewall, protecciones contra fuerza bruta y auditoría de puertos activos.

## 📋 Prerrequisitos
- Acceso **root** o privilegios de **sudo** en el VPS.
- Sistema Operativo: Ubuntu 20.04/22.04/24.04 (Noble) o Debian 11/12.
- Conexión a internet para descargar paquetes de los repositorios oficiales.

---

## 🏗️ Implementación Paso a Paso

### 1. Preparar el script en el VPS
Transfiere el archivo `install_security.sh` al VPS o créalo manualmente:

```bash
nano install_security.sh
# Pega el contenido del script y guarda (Ctrl+O, Enter, Ctrl+X)
```

### 2. Otorgar permisos de ejecución
```bash
chmod +x install_security.sh
```

### 3. Ejecutar el instalador como root
```bash
sudo ./install_security.sh
```

---

## 🛡️ ¿Qué herramientas instala y configura?

El instalador configura cuatro pilares fundamentales para el monitoreo de seguridad:

1.  **UFW (Uncomplicated Firewall):**
    - Activa el firewall del sistema.
    - Bloquea todo el tráfico entrante por defecto.
    - Permite automáticamente los puertos:
        - `22/tcp` (SSH)
        - `9100/tcp` (Node Exporter)
        - `8080/tcp` (cAdvisor)
        - `8501/tcp` (Aigents Pulse Master)

2.  **Fail2Ban:**
    - Protege contra ataques de fuerza bruta.
    - Monitorea `/var/log/auth.log` y banea IPs después de 5 intentos fallidos de SSH durante 1 hora.

3.  **Auditd (Linux Audit System):**
    - Permite al "Global Security Audit" rastrear eventos críticos y cambios en la configuración del sistema.

4.  **Nmap:**
    - Utilizado internamente por el motor de Aigents Pulse para realizar escaneos de sigilo (stealth scans) y detectar puertos abiertos no autorizados.

---

## ✅ Verificación de la Instalación

Para asegurar que todo funciona correctamente, ejecute estos comandos en el VPS:

- **Verificar Firewall:** `sudo ufw status verbose`
- **Verificar Fail2Ban:** `sudo fail2ban-client status sshd`
- **Verificar Auditoría:** `sudo service auditd status`
- **Verificar Nmap:** `nmap --version`

---

## 🛠️ Solución de Problemas

### Error de Dependencias (Ubuntu 24.04 Noble)
Si anteriormente intentó instalar `iptables-persistent` junto con `ufw`, es posible que el sistema muestre conflictos. El instalador v3.1 ha sido corregido para usar **únicamente UFW**, ya que este maneja su propia persistencia de reglas de forma nativa en las versiones modernas de Ubuntu.

### Acceso denegado a Docker
Si bien este script no instala Docker (eso lo hace `install.sh`), si cAdvisor no reporta datos después de activar el firewall, asegúrese de reiniciar Docker para que sus reglas de IPTables se reapliquen correctamente:
```bash
sudo systemctl restart docker
```

---
**Desarrollado por:** Ing. Ángel David Yaguana | Aigents Solutions  
**Postura de Seguridad:** Spectre+ (Vigilancia Total)
