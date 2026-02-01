import socket
import time
import threading
import sqlite3
import smtplib
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from email.mime.text import MIMEText

# Fix for Python 3.12+ sqlite3 datetime deprecation
def adapt_datetime(val):
    return val.isoformat()

def convert_datetime(val):
    return datetime.fromisoformat(val.decode())

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

# Configuration
DB_NAME = "aigentss_pulse.db"
DEFAULT_INTERVAL = 60
EMAIL_SENDER = "angel.yaguana@aigentss.com"
EMAIL_PASS = os.getenv('EMAIL_PASS')
EXPORT_DIR = "exports"

# Initial Seed List (Migrated to DB on first run)
INITIAL_VPS_LIST = {
    "9rounds": "217.76.58.149",
    "Quitomotors": "194.163.160.139",
    "Armacar": "109.199.117.80",
    "Kia": "62.84.187.169",
    "Hyundai": "54.38.191.168",
    "Autocom": "154.38.191.23",
    "1001Talleres": "147.93.179.212"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
                  timestamp DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # New Table: Dynamic VPS Targets (with PORT)
    c.execute('''CREATE TABLE IF NOT EXISTS vps_targets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  ip TEXT,
                  port INTEGER DEFAULT 22,
                  enabled INTEGER DEFAULT 1,
                  notify INTEGER DEFAULT 1)''')
    
    # Schema Migration: Add 'port' column if missing
    try:
        c.execute("ALTER TABLE vps_targets ADD COLUMN port INTEGER DEFAULT 22")
    except sqlite3.OperationalError:
        pass # Column likely exists
    
    # Seed Config
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('check_interval', ?)", (str(DEFAULT_INTERVAL),))
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('global_notify', '1')")
    
    # Seed VPS List if empty
    c.execute("SELECT count(*) FROM vps_targets")
    if c.fetchone()[0] == 0:
        logging.info("Seeding database with initial VPS list...")
        for name, ip in INITIAL_VPS_LIST.items():
            c.execute("INSERT INTO vps_targets (name, ip, port) VALUES (?, ?, 22)", (name, ip))
            
    conn.commit()
    conn.close()

    # Exports Directory
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

def get_config_int(key, default):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key=?", (key,))
        result = c.fetchone()
        conn.close()
        return int(result[0]) if result else default
    except Exception as e:
        logging.error(f"Error reading config {key}: {e}")
        return default

def get_active_targets():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, ip, port, notify FROM vps_targets WHERE enabled=1")
        targets = c.fetchall() # [(name, ip, port, notify), ...]
        conn.close()
        return targets
    except Exception as e:
        logging.error(f"Error reading targets: {e}")
        return []

def send_alert(vps_name, vps_ip, error_msg):
    if not EMAIL_PASS:
        # logging.warning("EMAIL_PASS environment variable not set. Skipping email alert.") 
        # Commented out to reduce noise in logs if intentionally unset
        return

    subject = f"ALERT: VPS {vps_name} is DOWN"
    body = f"Aigentss Pulse Alert\n\nThe VPS {vps_name} ({vps_ip}) is unreachable or failed protocol check.\n\nError: {error_msg}\n\nTime: {datetime.now()}"
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER

    try:
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        server = smtplib.SMTP(smtp_host, 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASS)
        server.sendmail(EMAIL_SENDER, EMAIL_SENDER, msg.as_string())
        server.quit()
        logging.info(f"Alert sent for {vps_name}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def should_send_alert(name, target_notify):
    # Check Global Switch
    global_notify = get_config_int('global_notify', 1)
    if global_notify == 0:
        return False
    
    # Check Per-VPS Switch
    if target_notify == 0:
        return False

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status FROM status_history WHERE name=? ORDER BY timestamp DESC LIMIT 1", (name,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        return True
    if result[0] == 1:
        return True
    return False

def check_vps(name, ip, port, notify_flag):
    status = 0
    latency = 0.0
    error_msg = ""
    
    try:
        start_time = time.time()
        # SSH Banner Verification
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0) # 2 seconds timeout
        sock.connect((ip, int(port)))
        
        # Read the banner
        banner = sock.recv(1024).decode('utf-8', errors='ignore')
        sock.close()
        
        latency = (time.time() - start_time) * 1000 # ms
        
        if banner.startswith("SSH-"):
            status = 1
            logging.info(f"{name} ({ip}:{port}): UP, Latency: {latency:.2f}ms")
        else:
            status = 0
            error_msg = f"Protocol Error: Banner '{banner.strip()}' does not start with SSH-"
            logging.warning(f"{name} ({ip}:{port}): DOWN. {error_msg}")
            
    except Exception as e:
        status = 0
        latency = 0.0
        error_msg = str(e)
        logging.warning(f"{name} ({ip}:{port}): DOWN. Error: {e}")
    
    if status == 0 and should_send_alert(name, notify_flag):
        send_alert(name, ip, error_msg)

    log_to_db(name, ip, status, latency)

def log_to_db(name, ip, status, latency):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO status_history (name, ip, status, latency, timestamp) VALUES (?, ?, ?, ?, ?)",
              (name, ip, status, latency, datetime.now()))
    conn.commit()
    conn.close()

def save_to_csv():
    """Dumps the ENTIRE history table to CSV automatically."""
    try:
        conn = sqlite3.connect(DB_NAME)
        # Select all data
        query = "SELECT * FROM status_history ORDER BY timestamp DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        output_path = os.path.join(EXPORT_DIR, "pulse_history.csv")
        df.to_csv(output_path, index=False)
        logging.info(f"Full history dumped to {output_path}")
    except Exception as e:
        logging.error(f"CSV Export failed: {e}")

def purge_old_data():
    """Deletes records older than 30 days."""
    try:
        retention_days = 30
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM status_history WHERE timestamp < ?", (cutoff_date,))
        deleted_count = c.rowcount
        conn.commit()
        conn.close()
        if deleted_count > 0:
            logging.info(f"Purged {deleted_count} records older than {retention_days} days.")
    except Exception as e:
        logging.error(f"Purge failed: {e}")

def monitor_loop():
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
        purge_old_data()
            
        interval = get_check_interval()
        logging.info(f"Sleeping for {interval} seconds...")
        time.sleep(interval)

# Helper for interval (re-added inside to avoid undefined error if moved)
def get_check_interval():
    return get_config_int('check_interval', 60)

if __name__ == "__main__":
    init_system()
    logging.info("Starting Aigentss Pulse Core...")
    monitor_loop()
