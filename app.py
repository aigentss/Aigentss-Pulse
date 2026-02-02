import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import subprocess
import signal
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

# Configuration
DB_NAME = "aigentss_pulse.db"
LOGO_FILE = "Logo_1024.png"
LOGO_URL = "https://aigentss.com/wp-content/uploads/2023/11/logo-aigentss.png"
KEY_FILE = "secret.key"

st.set_page_config(page_title="Aigentss Pulse | Infrastructure Core", layout="wide", page_icon="📡")

# Custom CSS for Aigentss Pulse Elite
st.markdown("""
<style>
    .metric-card {
        background-color: #333333;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #41424C;
        text-align: center;
        margin-bottom: 20px;
        color: white;
    }
    .status-dot {
        height: 15px;
        width: 15px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 10px;
    }
    .status-online { color: #00ff00; }
    .status-warning { color: #FFA500; }
    .status-offline { color: #ff0000; }
    
    .card-online { border-left: 5px solid #00ff00; }
    .card-warning { border-left: 5px solid #FFA500; }
    .card-offline { border-left: 5px solid #ff0000; box-shadow: 0 0 10px rgba(255, 0, 0, 0.2); }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #0E1117;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Security Logic
def load_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        return None 

def encrypt_val(val):
    key = load_key()
    if not key:
        st.error("Encryption key not found. Please restart monitor.py to generate it.")
        return None
    cipher_suite = Fernet(key)
    return cipher_suite.encrypt(val.encode()).decode()

def get_db_connection():
    return sqlite3.connect(DB_NAME)

def get_latest_status():
    try:
        conn = get_db_connection()
        query = """
        SELECT name, ip, status, latency, MAX(timestamp) as last_check
        FROM status_history
        GROUP BY name
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def get_config_value(key, default):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key=?", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else default
    except:
        return default

def set_config_value(key, val):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()

def get_targets():
    try:
        conn = get_db_connection()
        # Ensure backwards compatibility if port column missing (handled in monitor.py migration)
        try:
            df = pd.read_sql_query("SELECT id, name, ip, port, enabled, notify FROM vps_targets", conn)
        except:
             df = pd.read_sql_query("SELECT id, name, ip, enabled, notify FROM vps_targets", conn)
             df['port'] = 22 # Default for display if old schema used app before restart
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['id', 'name', 'ip', 'port', 'enabled', 'notify'])

def add_target(name, ip, port=22):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO vps_targets (name, ip, port) VALUES (?, ?, ?)", (name, ip, int(port)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error adding target: {e}")
        return False

def update_target(id, enabled, notify):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE vps_targets SET enabled=?, notify=? WHERE id=?", (1 if enabled else 0, 1 if notify else 0, id))
    conn.commit()
    conn.close()

def delete_target(id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vps_targets WHERE id=?", (id,))
    conn.commit()
    conn.close()

def get_history_data(start_time=None, end_time=None):
    try:
        conn = get_db_connection()
        
        if not start_time:
            start_time = datetime.now() - timedelta(hours=24)
        
        # Optimization: Limit points if range is huge (simple sampling via SQLite not easy without window functions, 
        # but 7 days at 1m interval is ~10k points per server, manageable for Streamlit charts usually)
        # Using basic select for now, index on timestamp helps speed.
        
        query = "SELECT name, latency, timestamp FROM status_history WHERE timestamp >= ?"
        params = [start_time]
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
            
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        return pd.DataFrame()

def check_monitor_health():
    """Auto-healing: Checks if data is stale and restarts monitor if needed."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT MAX(timestamp) FROM status_history")
        last_check = c.fetchone()[0]
        conn.close()

        if last_check:
            last_time = datetime.fromisoformat(last_check)
            gap = (datetime.now() - last_time).total_seconds()
            
            # If gap > 2 mins (assuming 60s interval standard, allowing slight delay)
            if gap > 120:
                st.toast("⚠️ Monitor heartbeat lost. Attempting restart...", icon="🚑")
                try:
                    subprocess.Popen(["python3", "monitor.py"])
                    time.sleep(2) # Give it moment to spawn
                    st.toast("✅ Monitor restarted.", icon="🚀")
                    return False
                except Exception as e:
                    st.error(f"Failed to auto-start monitor: {e}")
                    return False
        return True
    except:
        return True # DB empty or error, assume initializing

# Sidebar Styling
try:
    st.sidebar.image(LOGO_FILE, use_container_width=True)
except:
    st.sidebar.image(LOGO_URL, use_container_width=True)

st.sidebar.markdown("<h3 style='text-align: center; color: #FAFAFA;'>Aigentss Pulse</h3>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.header("Settings")

# Interval Setting
current_interval = int(get_config_value('check_interval', 60))
new_interval = st.sidebar.slider("Check Interval (seconds)", min_value=10, max_value=300, value=current_interval)
if new_interval != current_interval:
    set_config_value('check_interval', new_interval)
    st.sidebar.success(f"Optimizing engine to {new_interval}s...")
    time.sleep(0.5)
    st.rerun()

# Run Health Check
check_monitor_health()

# Main Title
st.title("Aigentss Pulse | Infrastructure Core")

# Tabs
tab1, tab2 = st.tabs(["📡 Live Dashboard", "⚙️ Configuration"])

with tab1:
    # Live Status
    st.subheader("Live Status")
    df_status = get_latest_status()
    
    if not df_status.empty:
        cols = st.columns(4)
        for index, row in df_status.iterrows():
            col_idx = index % 4
            if index > 0 and index % 4 == 0:
                cols = st.columns(4)
            
            with cols[col_idx]:
                if row['status'] == 1:
                    if row['latency'] > 500:
                        status_class = "warning"
                        dot_color = "#FFA500"
                        card_class = "card-warning"
                    else:
                        status_class = "online"
                        dot_color = "#00ff00"
                        card_class = "card-online"
                else:
                    status_class = "offline"
                    dot_color = "#ff0000"
                    card_class = "card-offline"
                
                st.markdown(f"""
                <div class="metric-card {card_class}">
                    <div style="font-size: 1.2em; font-weight: bold; margin-bottom: 5px;">
                        <span class="status-dot" style="background-color: {dot_color};"></span>
                        {row['name']}
                    </div>
                    <div style="color: #888; font-size: 0.9em; margin-bottom: 15px;">{row['ip']}</div>
                    <div style="font-size: 2em; font-weight: bold; margin-bottom: 5px;">
                        {row['latency']:.1f} ms
                    </div>
                    <div style="font-size: 0.8em; color: #666;">
                        Last check: {row['last_check']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("No data received yet. Initializing Pulse Core...")

    # Analytics & Filters
    st.markdown("---")
    st.subheader("📈 Historical Analytics")
    
    c1, c2 = st.columns([3, 1])
    with c1:
        time_range = st.select_slider(
            "Time Range",
            options=["10m", "30m", "1h", "6h", "12h", "24h", "48h", "7d", "Custom"],
            value="24h"
        )
    
    start_time = None
    end_time = None
    
    if time_range == "Custom":
        with c2:
            date_range = st.date_input("Select Date Range", [])
            if len(date_range) == 2:
                start_time = datetime.combine(date_range[0], datetime.min.time())
                end_time = datetime.combine(date_range[1], datetime.max.time())
    else:
        now = datetime.now()
        mapping = {
            "10m": timedelta(minutes=10), "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "12h": timedelta(hours=12), "24h": timedelta(hours=24),
            "48h": timedelta(hours=48), "7d": timedelta(days=7)
        }
        start_time = now - mapping.get(time_range, timedelta(hours=24))

    if start_time:
        df_history = get_history_data(start_time, end_time)
        if not df_history.empty:
            st.line_chart(df_history, x="timestamp", y="latency", color="name")
        else:
            st.info("No data available for the selected range.")
        
    if st.button("Refresh Dashboard"):
        st.rerun()

with tab2:
    st.header("System Configuration")
    
    # Secure SMTP Settings
    st.subheader("🔐 Security Layer (SMTP)")
    with st.expander("Configure Email Credentials"):
        smtp_user = st.text_input("Monitoring Email (Gmail)", value=get_config_value("email_user", ""))
        smtp_pass = st.text_input("App Password", type="password")
        
        if st.button("Save Credentials"):
            if smtp_user and smtp_pass:
                set_config_value("email_user", smtp_user)
                encrypted = encrypt_val(smtp_pass)
                if encrypted:
                    set_config_value("email_pass", encrypted)
                    st.success("Credentials secured and encrypted.")
            else:
                st.error("Please provide both email and password.")

    st.markdown("---")
    
    # Global Notification
    st.subheader("🔔 Notification Rules")
    global_notify = int(get_config_value('global_notify', 1))
    new_global_notify = st.toggle("Enable All Email Notifications", value=(global_notify == 1))
    
    if (new_global_notify and global_notify == 0) or (not new_global_notify and global_notify == 1):
        set_config_value('global_notify', 1 if new_global_notify else 0)
        st.success("Global notification setting updated.")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    
    # Manage VPS Targets
    st.subheader("🖥️ Manage VPS Targets")
    
    # Add New VPS
    with st.expander("Add New VPS"):
        with st.form("add_vps_form"):
            c1, c2, c3 = st.columns([3, 3, 2])
            new_name = c1.text_input("Server Name")
            new_ip = c2.text_input("IP Address")
            new_port = c3.number_input("Port", min_value=1, max_value=65535, value=22)
            submitted = st.form_submit_button("Add VPS")
            
            if submitted:
                if new_name and new_ip:
                    if add_target(new_name, new_ip, new_port):
                        st.success(f"Added {new_name}")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("Please provide Name and IP.")
    
    # List/Edit VPS
    st.write("Existing Targets:")
    df_targets = get_targets()
    
    if not df_targets.empty:
        # Header
        h1, h2, h3, h4, h5, h6 = st.columns([3, 3, 2, 2, 2, 2])
        h1.write("**Name**")
        h2.write("**IP**")
        h3.write("**Port**")
        h4.write("**Monitoring**")
        h5.write("**Notifications**")
        h6.write("**Action**")
        
        for index, row in df_targets.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 2, 2, 2, 2])
            c1.write(row['name'])
            c2.write(row['ip'])
            c3.write(str(row['port']))
            
            # Toggles
            is_enabled = c4.checkbox("On", value=bool(row['enabled']), key=f"en_{row['id']}")
            is_notify = c5.checkbox("Alerts", value=bool(row['notify']), key=f"not_{row['id']}")
            
            # Update logic check
            if is_enabled != bool(row['enabled']) or is_notify != bool(row['notify']):
                update_target(row['id'], is_enabled, is_notify)
                st.toast(f"Updated {row['name']}")
                
            # Delete
            if c6.button("🗑️", key=f"del_{row['id']}"):
                delete_target(row['id'])
                st.rerun()
    else:
        st.info("No targets configured.")
        
# Footer
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666;'>© 2026 Aigentss. All systems nominal.</div>", unsafe_allow_html=True)
