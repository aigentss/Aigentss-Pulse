import prometheus_metrics
import socket
import time
import threading
import sqlite3
import smtplib
import os
import logging
import pandas as pd
import io
import json
import matplotlib.pyplot as plt
import concurrent.futures
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from cryptography.fernet import Fernet

# Fix for Python 3.12+ sqlite3 datetime deprecation
def adapt_datetime(val):
    return val.isoformat()

def convert_datetime(val):
    return datetime.fromisoformat(val.decode())

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

# Configuration
DB_NAME = "aigentss_pulse.db"
KEY_FILE = "secret.key"
EXPORT_DIR = "exports"

# Initial Seed List (Migrated to DB on first run)
INITIAL_VPS_LIST = {
    "9rounds": "217.76.58.149",
    "Quitomotors": "194.163.160.139",
    "Armacar": "109.199.117.80",
    "Kia": "62.84.187.169",
    "Hyundai": "154.38.191.168",
    "Autocom": "154.38.191.23",
    "1001Talleres": "147.93.179.212",
    "VPS-Testing": "82.25.84.232",
    "IA LOCAL": "192.168.100.33",
    "AGENTE C1": "192.168.100.71"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_or_create_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
        return key

CIPHER_SUITE = Fernet(load_or_create_key())

def init_system():
    # Database Setup
    conn = sqlite3.connect(DB_NAME)
    
    # Pragma for Idempotency and Performance
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS status_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  ip TEXT,
                  status INTEGER,
                  latency REAL,
                  cpu REAL DEFAULT 0,
                  ram REAL DEFAULT 0,
                  disk REAL DEFAULT 0,
                  timestamp DATETIME)''')
    
    # Migration handling
    try:
        c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='vps_targets'")
        table_exists = c.fetchone()[0]
        
        # Check if vps_targets has primary key ip by checking typical failure or schema
        # For simplicity, we create if not exists or ensure fields.
        c.execute('''CREATE TABLE IF NOT EXISTS vps_targets
                     (name TEXT,
                      ip TEXT PRIMARY KEY,
                      port INTEGER DEFAULT 9100,
                      enabled INTEGER DEFAULT 1,
                      notify INTEGER DEFAULT 1)''')
    except Exception as e:
        logging.warning(f"Table migration exception: {e}")

    # Docker Metrics Snapshot Table
    c.execute('''CREATE TABLE IF NOT EXISTS docker_snapshot
                 (ip TEXT PRIMARY KEY,
                  json_data TEXT,
                  updated_at DATETIME)''')

    # Config & Notification Logs
    c.execute('''CREATE TABLE IF NOT EXISTS notification_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  recipient_email TEXT,
                  vps_name TEXT,
                  status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Indices
    c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON status_history(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ip ON status_history(ip)")
    
    # Seeds
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('check_interval', '60')")
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('global_notify', '1')")
    
    for name, ip in INITIAL_VPS_LIST.items():
        c.execute("INSERT OR IGNORE INTO vps_targets (name, ip, port) VALUES (?, ?, 9100)", (name, ip))
        c.execute("UPDATE vps_targets SET name=? WHERE ip=?", (name, ip))
            
    conn.commit()
    conn.close()

    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

def get_config_val(key, default=None):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key=?", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else default
    except:
        return default

def get_decrypted_config(key):
    val = get_config_val(key)
    if not val: return None
    try: return CIPHER_SUITE.decrypt(val.encode()).decode()
    except: return None

def get_active_targets():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, ip, port, notify FROM vps_targets WHERE enabled=1")
        targets = c.fetchall()
        conn.close()
        return targets
    except: return []

def create_latency_graph(ip):
    """PNG 24h graph."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cutoff = datetime.now() - timedelta(hours=24)
        df = pd.read_sql_query("SELECT timestamp, latency FROM status_history WHERE ip=? AND timestamp >= ? ORDER BY timestamp ASC", 
                               conn, params=(ip, cutoff))
        conn.close()
        if df.empty: return None
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        plt.figure(figsize=(8, 4))
        plt.plot(df['timestamp'], df['latency'], color='#ff0000', linewidth=2)
        plt.title(f"Latency Trend (Last 24h) - {ip}", color='white')
        plt.gca().set_facecolor('#1e1e1e')
        plt.gcf().set_facecolor('#1e1e1e')
        plt.tick_params(colors='white')
        img_data = io.BytesIO()
        plt.savefig(img_data, format='png', bbox_inches='tight', facecolor='#1e1e1e')
        plt.close()
        img_data.seek(0)
        return img_data.read()
    except Exception as e:
        logging.error(f"Graph error: {e}")
        return None

def send_alert_worker(vps_name, vps_ip, error_msg):
    """Elite Async Alert."""
    email_user = get_config_val('email_user')
    email_pass = get_decrypted_config('email_pass')
    if not email_user or not email_pass: return

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT cpu, ram, disk, timestamp FROM status_history WHERE ip=? AND status=1 ORDER BY timestamp DESC LIMIT 1", (vps_ip,))
    last_up = c.fetchone()
    conn.close()

    vitals = f"CPU: {last_up[0]:.0f}% | RAM: {last_up[1]:.0f}% | DISK: {last_up[2]:.0f}%" if last_up else "Unknown"
    ts = last_up[3] if last_up else "None"

    msg = MIMEMultipart()
    msg['Subject'] = f"🚨 ALERT: {vps_name} is DOWN"
    msg['From'] = email_user
    msg['To'] = email_user
    body = f"""
🐒 Aigentss Pulse | Intelligence Report
SERVER: {vps_name} ({vps_ip})
STATUS: 🔴 DOWN (Port 9100 Stealth)

LAST HEARTBEAT (TS): {ts}
LAST VITALS: {vitals}
ERROR: {error_msg}

24h trend graph attached.
"""
    msg.attach(MIMEText(body, 'plain'))
    graph = create_latency_graph(vps_ip)
    if graph: msg.attach(MIMEImage(graph, name="trend.png"))

    try:
        s = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        s.starttls()
        s.login(email_user, email_pass)
        s.sendmail(email_user, email_user, msg.as_string())
        s.quit()
        logging.info(f"Elite alert sent: {vps_name}")
    except Exception as e:
        logging.error(f"Alert failed: {e}")

def send_alert(name, ip, msg):
    threading.Thread(target=send_alert_worker, args=(name, ip, msg), daemon=True).start()

def should_send_alert(ip, target_notify):
    if int(get_config_val('global_notify', 1)) == 0 or target_notify == 0: return False
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Check previous status to only alert on transition UP -> DOWN
    c.execute("SELECT status FROM status_history WHERE ip=? ORDER BY timestamp DESC LIMIT 1", (ip,))
    res = c.fetchone()
    conn.close()
    
    # If no history, assume UP to trigger alert on first down? 
    # Or assume invalid to avoid spam on startup. Let's send if previous was UP (1).
    if res and res[0] == 1:
        return True
    return False

def check_vps(name, ip, notify_flag):
    # Port 9100 Stealth Monitoring
    port = 9100
    try:
        start = time.time()
        # 1. TCP Connect Check
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(7.0)
        s.connect((ip, port)); s.close()
        latency = (time.time() - start) * 1000
        
        # 2. Prometheus Metrics
        vit = prometheus_metrics.get_node_metrics(ip)
        log_to_db(name, ip, 1, latency, vit['cpu'], vit['ram'], vit['disk'])
        
        # 3. Docker Metrics (Fetch and store snapshot)
        docker_stats = prometheus_metrics.get_docker_metrics(ip)
        if docker_stats:
            log_docker_snapshot(ip, docker_stats)
            
        logging.info(f"{name} ({ip}): UP [Bypass] - {latency:.2f}ms")
    except Exception as e:
        if should_send_alert(ip, notify_flag): 
            send_alert(name, ip, str(e))
        log_to_db(name, ip, 0, 0, 0, 0, 0)
        logging.warning(f"{name} ({ip}): DOWN - {e}")

def log_to_db(name, ip, status, lat, cpu, ram, disk):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO status_history (name, ip, status, latency, cpu, ram, disk, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (name, ip, status, lat, cpu, ram, disk, datetime.now()))
    conn.commit(); conn.close()

def log_docker_snapshot(ip, data):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    json_str = json.dumps(data)
    c.execute("INSERT OR REPLACE INTO docker_snapshot (ip, json_data, updated_at) VALUES (?, ?, ?)",
              (ip, json_str, datetime.now()))
    conn.commit(); conn.close()

# --- THREAD MANAGEMENT ---
_monitor_thread = None
_monitor_lock = threading.Lock()

def start_monitor_thread():
    """Thread-safe singleton starter for the monitor loop."""
    global _monitor_thread
    with _monitor_lock:
        if _monitor_thread is None or not _monitor_thread.is_alive():
            _monitor_thread = threading.Thread(target=master_loop, daemon=True)
            _monitor_thread.start()
            logging.info("Background monitor thread spawned.")
        else:
            logging.debug("Monitor thread already active.")

def master_loop():
    init_system()
    while True:
        targets = get_active_targets()
        interval = int(get_config_val('check_interval', 60))
        
        # Concurrency de Élite: ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_vps, t[0], t[1], t[3]) for t in targets]
            concurrent.futures.wait(futures)
            
        time.sleep(interval)

if __name__ == "__main__":
    master_loop()
