# Prompt Maestro: Desarrollo Integral de Aigentss Pulse v2.0

Actúa como un **Arquitecto de Software Senior (Python/DevOps)** y un experto en **Diseño UI/UX**. Tu objetivo es construir desde cero la aplicación **Aigentss Pulse v2.0**, una plataforma de observabilidad para infraestructura VPS y Docker.

Debes entregar el proyecto completo, funcional y listo para producción, siguiendo las especificaciones detalladas a continuación.

## 1. Arquitectura y Estructura del Proyecto

**Stack Tecnológico:**
- **Lenguaje**: Python 3.10+
- **Frontend**: Streamlit (Gestión de estado y UI reactiva).
- **Backend/Worker**: `threading` + `concurrent.futures` (Singleton Pattern).
- **Persistencia**: SQLite3 (Modo WAL para alta concurrencia).
- **Criptografía**: `cryptography.fernet` para secretos.
- **Visualización**: `matplotlib` (para reportes estáticos) y `streamlit.line_chart` (interactivo).

**Estructura del Directorio:**
```text
/
├── app.py                 # Punto de entrada UI (Streamlit)
├── monitor.py             # Lógica de monitoreo en segundo plano (Daemon Thread)
├── prometheus_metrics.py  # Módulo de extracción de métricas (Scraper)
├── requirements.txt       # Dependencias
├── instrucciones.md       # Guía de instalación para los VPS clientes
└── .github/workflows/streamlit-deploy.yml # Pipeline CI/CD
```

## 2. Requerimientos de Backend (`monitor.py` y `prometheus_metrics.py`)

### A. Lógica de Monitoreo (The Engine)
1.  **Concurrencia**: Implementar un hilo demonio (`daemon thread`) que ejecute un ciclo infinito. Dentro de cada ciclo, utiliza `ThreadPoolExecutor` para chequear múltiples VPS en paralelo.
2.  **Base de Datos**:
    *   Usar SQLite (`aigentss_pulse.db`).
    *   Configuración crítica: `PRAGMA journal_mode=WAL` y `PRAGMA synchronous=NORMAL` para evitar bloqueos de base de datos entre el hilo de escritura y la lectura de la UI.
    *   Tablas: `status_history`, `vps_targets`, `config`, `docker_snapshot`.
3.  **Persistencia de Configuración**: Guardar preferencias (tema, intervalo de refresco) en la tabla `config` para que persistan tras reiniciar.

### B. Extracción de Métricas (The Scraper)
1.  **Stealth Monitoring**: Intentar conexión TCP al puerto 9100. Si responde, marcar como UP "Bypass".
2.  **Prometheus Node Exporter**: Scrapear `/metrics` en puerto 9100 para obtener CPU, RAM y Disco.
3.  **Docker Drill-Down**:
    *   Intentar scrapear métricas de cAdvisor primero en puerto **8080**, y hacer fallback al **9100**.
    *   Extraer `container_memory_usage_bytes` y `container_cpu_usage_seconds_total`.
    *   Guardar un snapshot JSON en la tabla `docker_snapshot`.

### C. Sistema de Alertas
1.  **SMTP Seguro**: Enviar correos vía Gmail (Puerto 587, TLS) solo cuando un servidor cambia de estado UP a DOWN.
2.  **Adjuntos**: Generar un gráfico PNG de la tendencia de latencia de las últimas 24h usando `matplotlib` en memoria (`io.BytesIO`) y adjuntarlo al correo.

## 3. Requerimientos de Frontend UI/UX (`app.py`)

### A. Diseño y Estética (Aesthetic WOW)
Implementar un sistema de temas persistente (guardado en DB) configurable desde el panel:

1.  **Modo Oscuro ("Infinity" - Default)**:
    *   Fondo: `#121212` (Material Dark).
    *   Tarjetas: `#1E1E1E` con bordes sutiles `1px solid rgba(255,255,255,0.1)`.
    *   Efecto Neon: Sombras verdes (`#00ff00`) para estado UP.
2.  **Modo Claro ("Daywalker")**:
    *   Fondo: `#F4F4F4` (Gris profesional).
    *   Tarjetas: `#FFFFFF` (Blanco puro para profundidad).
    *   Texto: `#333333` (Gris oscuro).
3.  **Inyección CSS**: Usar `st.markdown` con `unsafe_allow_html=True` para forzar estilos en clases `.stApp`, `.vps-card`, y barras de progreso personalizadas.

### B. Navegación y Funcionalidad
La aplicación debe tener 4 pestañas (`st.tabs`):
1.  **🚀 Status Live**: Grid de tarjetas. Cada tarjeta muestra estado, latencia y 3 barras de progreso (CPU, RAM, Disco). Debe tener un expander "🐳 Docker Drill Down" que muestre contenedores activos.
2.  **📈 Graficas (Analytics)**: Dashboard con 4 gráficos de línea (Latencia, CPU, RAM, Disco) mostrando histórico de 24h. Debe incluir un `multiselect` para filtrar por VPS.
3.  **⚙️ Nucleus Config**: Panel para:
    *   Cambiar Tema (Light/Dark).
    *   Ajustar Frecuencia de Muestreo (Slider).
    *   Gestionar Credenciales SMTP (Cifradas con Fernet).
    *   Añadir/Eliminar VPS de la lista.
4.  **📜 History & Export**: Tabla de datos crudos y botón de descarga CSV.

## 4. Entregables de DevOps y Soporte

### A. Dependencias (`requirements.txt`)
```text
streamlit
pandas
cryptography
matplotlib
requests
psutil
prometheus-api-client
```

### B. Guía de Instalación (`instrucciones.md`)
Generar un archivo Markdown que explique paso a paso cómo instalar **Node Exporter** (puerto 9100) y **cAdvisor** (Docker, puerto 8080) en los servidores remotos Ubuntu/Debian, incluyendo configuración de firewall `ufw`.

### C. Automatización (`.github/workflows/streamlit-deploy.yml`)
Configurar un workflow de GitHub Actions que se dispare en push a la rama principal, instale Python 3.10, dependencias y ejecute un linter (`flake8`).

---

**Instrucción Final:** Genera el código completo para todos los archivos mencionados, asegurando que `monitor.py` se integra como un módulo dentro de `app.py` para levantar el hilo en segundo plano automáticamente al iniciar la aplicación web.
