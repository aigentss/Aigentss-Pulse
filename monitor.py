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
import matplotlib.pyplot as plt
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
    "IA LOCAL": "192.168.100.33"
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
    
    # Schema Migration for Telemetry
    try:
        c.execute("ALTER TABLE status_history ADD COLUMN cpu REAL DEFAULT 0")
        c.execute("ALTER TABLE status_history ADD COLUMN ram REAL DEFAULT 0")
        c.execute("ALTER TABLE status_history ADD COLUMN disk REAL DEFAULT 0")
    except:
        pass # Columns exist

    # Performance Index for Analytics
    c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON status_history(timestamp)")
    # Index for IP queries (Source of Truth)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ip ON status_history(ip)")
    
    # Notification Logs
    c.execute('''CREATE TABLE IF NOT EXISTS notification_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  recipient_email TEXT,
                  vps_name TEXT,
                  status TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # New Table: Dynamic VPS Targets (IP as Primary Key / Unique)
    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='vps_targets'")
    table_exists = c.fetchone()[0]

    if table_exists:
        # Check if we need to migrate to IP as PK
        try:
            # Check for name Hyundai on Testing IP for deduplication
            c.execute("DELETE FROM vps_targets WHERE ip='82.25.84.232' AND name='Hyundai'")
            
            c.execute("CREATE TABLE IF NOT EXISTS vps_targets_new (name TEXT, ip TEXT PRIMARY KEY, port INTEGER DEFAULT 9100, enabled INTEGER DEFAULT 1, notify INTEGER DEFAULT 1)")
            c.execute("INSERT OR IGNORE INTO vps_targets_new (name, ip, port, enabled, notify) SELECT name, ip, 9100, enabled, notify FROM vps_targets")
            c.execute("DROP TABLE vps_targets")
            c.execute("ALTER TABLE vps_targets_new RENAME TO vps_targets")
        except Exception as e:
            logging.error(f"Migration error: {e}")
    else:
        c.execute('''CREATE TABLE vps_targets
                     (name TEXT,
                      ip TEXT PRIMARY KEY,
                      port INTEGER DEFAULT 9100,
                      enabled INTEGER DEFAULT 1,
                      notify INTEGER DEFAULT 1)''')

    # Seed Config
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('check_interval', '60')")
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('global_notify', '1')")
    
    # Seed VPS List
    logging.info("Checking/Seeding VPS Targets...")
    for name, ip in INITIAL_VPS_LIST.items():
        c.execute("INSERT OR IGNORE INTO vps_targets (name, ip, port) VALUES (?, ?, 9100)", (name, ip))
        # Enforce name
        c.execute("UPDATE vps_targets SET name=? WHERE ip=?", (name, ip))
            
    conn.commit()
    conn.close()

    # Exports Directory
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
    except Exception as e:
        logging.error(f"Error reading config {key}: {e}")
        return default

def get_decrypted_config(key):
    val = get_config_val(key)
    if not val:
        return None
    try:
        return CIPHER_SUITE.decrypt(val.encode()).decode()
    except Exception as e:
        logging.error(f"Decryption failed for {key}: {e}")
        return None

def get_active_targets():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, ip, port, notify FROM vps_targets WHERE enabled=1")
        targets = c.fetchall()
        conn.close()
        return targets
    except Exception as e:
        logging.error(f"Error reading targets: {e}")
        return []

def log_notification(email, vps_name, status):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO notification_logs (timestamp, recipient_email, vps_name, status) VALUES (?, ?, ?, ?)",
                  (datetime.now(), email, vps_name, status))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to log notification: {e}")

def create_latency_graph(ip):
    """Generates a PNG graph of the last 24h latency for a given IP."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cutoff = datetime.now() - timedelta(hours=24)
        df = pd.read_sql_query("SELECT timestamp, latency FROM status_history WHERE ip=? AND timestamp >= ? ORDER BY timestamp ASC", 
                               conn, params=(ip, cutoff))
        conn.close()
        
        if df.empty:
            return None
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        plt.figure(figsize=(8, 4))
        plt.plot(df['timestamp'], df['latency'], color='#ff0000', linewidth=2)
        plt.title(f"Latency Trend (Last 24h) - {ip}", color='white')
        plt.xlabel("Time", color='white')
        plt.ylabel("Latency (ms)", color='white')
        plt.grid(True, linestyle='--', alpha=0.3)
        plt.gca().set_facecolor('#1e1e1e')
        plt.gcf().set_facecolor('#1e1e1e')
        plt.tick_params(colors='white')
        
        img_data = io.BytesIO()
        plt.savefig(img_data, format='png', bbox_inches='tight', facecolor='#1e1e1e')
        plt.close()
        img_data.seek(0)
        return img_data.read()
    except Exception as e:
        logging.error(f"Failed to generate graph for {ip}: {e}")
        return None

def send_alert_worker(vps_name, vps_ip, error_msg):
    """Elite Async Alert with Graph, Vitals and Last Heartbeat."""
    email_user = get_config_val('email_user')
    email_pass = get_decrypted_config('email_pass')

    if not email_user or not email_pass or email_user.strip() == "" or email_pass.strip() == "":
        return

    # Fetch Intelligence (Last Heartbeat & Vitals)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT cpu, ram, disk, timestamp FROM status_history 
                 WHERE ip=? AND status=1 ORDER BY timestamp DESC LIMIT 1""", (vps_ip,))
    last_up = c.fetchone()
    conn.close()

    vitals_str = "Unknown"
    heartbeat_str = "No record found"
    
    if last_up:
        cpu, ram, disk, ts = last_up
        vitals_str = f"CPU: {cpu:.1f}% | RAM: {ram:.1f}% | DISK: {disk:.1f}%"
        heartbeat_str = ts

    # Create Message
    msg = MIMEMultipart()
    msg['Subject'] = f"🚨 ALERT: {vps_name} is DOWN"
    msg['From'] = email_user
    msg['To'] = email_user

    body_text = f"""
🐒 Aigentss Pulse | Stealth Intelligence Report

SERVER: {vps_name}
IP ADDRESS: {vps_ip}
STATUS: 🔴 DOWN (Unreachable via Stealth Port 9100)
ERROR: {error_msg}

--- INTEL REPORT ---
LAST HEARTBEAT (TS): {heartbeat_str}
LAST KNOWN VITALS:
- {vitals_str}

A latency trend graph for the last 24 hours is attached to this report.
"""
    msg.attach(MIMEText(body_text, 'plain'))

    # Attach Graph
    graph_data = create_latency_graph(vps_ip)
    if graph_data:
        image = MIMEImage(graph_data)
        image.add_header('Content-ID', '<trend_graph>')
        image.add_header('Content-Disposition', 'attachment', filename='latency_trend.png')
        msg.attach(image)

    try:
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        server = smtplib.SMTP(smtp_host, 587, timeout=15)
        server.starttls()
        server.login(email_user, email_pass)
        server.sendmail(email_user, email_user, msg.as_string())
        server.quit()
        logging.info(f"Elite Alert sent for {vps_name}")
        log_notification(email_user, vps_name, "Sent (Elite)")
    except Exception as e:
        logging.error(f"Failed to send email for {vps_name}: {e}")
        log_notification(email_user, vps_name, f"Failed: {str(e)}")

def send_alert(vps_name, vps_ip, error_msg):
    threading.Thread(target=send_alert_worker, args=(vps_name, vps_ip, error_msg), daemon=True).start()

def should_send_alert(ip, target_notify):
    global_notify = int(get_config_val('global_notify', 1))
    if global_notify == 0 or target_notify == 0:
        return False

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status FROM status_history WHERE ip=? ORDER BY timestamp DESC LIMIT 1", (ip,))
    result = c.fetchone()
    conn.close()
    
    if result is None or result[0] == 1:
        return True
    return False

def check_vps(name, ip, port, notify_flag):
    max_retries = 3
    check_port = 9100 
    
    for attempt in range(1, max_retries + 1):
        status = 0
        latency = 0.0
        error_msg = ""
        cpu, ram, disk = 0, 0, 0

        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(7.0)
            sock.connect((ip, check_port))
            sock.close()
            
            latency = (time.time() - start_time) * 1000
            status = 1
            logging.info(f"{name} ({ip}): UP [Stealth Mode], Latency: {latency:.2f}ms")
            
            # Fetch telemetry
            vitals = prometheus_metrics.get_node_metrics(ip)
            cpu, ram, disk = vitals['cpu'], vitals['ram'], vitals['disk']
            
            log_to_db(name, ip, status, latency, cpu, ram, disk)
            return
                
        except Exception as e:
            error_msg = str(e)
            
        if attempt < max_retries:
            logging.warning(f"{name} ({ip}): Attempt {attempt} failed via 9100. Retrying...")
            time.sleep(2)
        else:
            logging.warning(f"{name} ({ip}): DOWN after {max_retries} stealth attempts.")
            if should_send_alert(ip, notify_flag):
                send_alert(name, ip, error_msg)
            log_to_db(name, ip, status, 0, 0, 0, 0)

def log_to_db(name, ip, status, latency, cpu, ram, disk):
    if latency < 0 or latency > 30000:
        return

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO status_history (name, ip, status, latency, cpu, ram, disk, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (name, ip, status, latency, cpu, ram, disk, datetime.now()))
    conn.commit()
    conn.close()

def generate_status_page():
    try:
        conn = sqlite3.connect(DB_NAME)
        query = "SELECT sh.name, sh.status, MAX(sh.timestamp) FROM status_history sh GROUP BY sh.ip"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        html = f"""
        <html><head><style>body{{font-family:sans-serif;background:#1e1e1e;color:#fff;padding:20px;}}
        .card{{background:#333;padding:15px;margin:10px 0;border-radius:5px;display:flex;justify-content:space-between;}}
        .online{{color:#0f0;}} .offline{{color:#f00;}}</style></head>
        <body><h1>Aigentss Pulse | Stealth Intelligence</h1>
        """
        for _, row in df.iterrows():
            st_text = "Modo Bypass" if row['status'] == 1 else "OFFLINE"
            st_class = "online" if row['status'] == 1 else "offline"
            html += f'<div class="card"><span>{row["name"]}</span><span class="{st_class}">{st_text}</span></div>'
        
        html += f"<p>Updated: {datetime.now()}</p></body></html>"
        with open(os.path.join(EXPORT_DIR, "status.html"), "w") as f:
            f.write(html)
    except Exception as e:
        logging.error(f"Status Page Gen Failed: {e}")

def save_to_csv():
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT * FROM status_history ORDER BY timestamp DESC", conn)
        conn.close()
        df.to_csv(os.path.join(EXPORT_DIR, "pulse_history.csv"), index=False)
        logging.info("History exported to CSV.")
    except Exception as e:
        logging.error(f"CSV Export failed: {e}")

def purge_old_data():
    try:
        cutoff = datetime.now() - timedelta(days=30)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM status_history WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Purge failed: {e}")

def master_loop():
    """Elite Unified Master Loop"""
    while True:
        targets = get_active_targets()
        threads = []
        for name, ip, port, notify in targets:
            t = threading.Thread(target=check_vps, args=(name, ip, port, notify))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
            
        save_to_csv()
        generate_status_page()
        purge_old_data()
        
        interval = int(get_config_val('check_interval', 60))
        logging.info(f"Stealth Watch Complete. Cycle: {interval}s")
        time.sleep(interval)

if __name__ == "__main__":
    init_system()
    logging.info("Aigentss Pulse | Stealth Intelligence Active")
    master_loop()
