# Aigentss Pulse | Infrastructure Core

Professional Agentless Monitoring System for Contabo VPS infrastructure.
Monitors SSH connectivity (Port 22/Custom) and Latency from a Hostinger VPS.

## Features
- **Deep SSH Verification**: Connects and verifies `SSH-` banner to prevent false positives.
- **Dynamic Management**: Add/Remove VPS and changing ports via UI.
- **Granular Alerts**: Global and Per-VPS email notification toggles.
- **Automated Intelligence**:
    - Auto-export full history to `exports/pulse_history.csv` after every scan.
    - Auto-purge data older than 30 days.

## Installation (Manual)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/aigentss/Aigentss-Pulse.git
   cd Aigentss-Pulse
   ```

2. **Install Dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Environment Setup**:
   Export your email password (App Password recommended).
   ```bash
   export EMAIL_PASS='your_password'
   ```

4. **Run**:
   - **Background Monitor**: `python3 monitor.py` (Use systemd for production).
   - **Dashboard**: `streamlit run app.py`.

## Automated Deployment (GitHub Actions)

This repository includes a CI/CD pipeline in `.github/workflows/deploy.yml`.

### Prerequisites
1. **Hostinger VPS**: Ensure you have SSH access.
2. **GitHub Secrets**: Go to **Settings > Secrets and variables > Actions** and add:
   - `HOST`: IP address of your Hostinger VPS.
   - `USERNAME`: SSH username (e.g., `root`).
   - `SSH_KEY`: Your private SSH key (PEM format).
   - `EMAIL_PASS`: Email password for alerts.

### Workflow
- Push to `main` triggers the deployment.
- The pipeline connects via SSH, pulls the latest code, updates dependencies, and restarts the `vps_monitor` service.

## Systemd Setup (Recommended)

Create `/etc/systemd/system/vps_monitor.service`:
```ini
[Unit]
Description=Aigentss Pulse Monitor
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Aigentss-Pulse
Environment="EMAIL_PASS=your_secret_password"
ExecStart=/usr/bin/python3 /root/Aigentss-Pulse/monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Data & Reports
- **Database**: `aigentss_pulse.db` (SQLite).
- **Reports**: `exports/pulse_history.csv` (Full history, updated every minute).
