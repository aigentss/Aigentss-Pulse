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
        # Enhanced query for latest status by IP (Core Truth)
        query = """
        SELECT sh.* 
        FROM status_history sh
        INNER JOIN (
            SELECT ip, MAX(timestamp) as MaxTime
            FROM status_history
            GROUP BY ip
        ) groupedsh 
        ON sh.ip = groupedsh.ip 
        AND sh.timestamp = groupedsh.MaxTime
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
        df = pd.read_sql_query("SELECT rowid as id, name, ip, port, enabled, notify FROM vps_targets", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['id', 'name', 'ip', 'port', 'enabled', 'notify'])

def add_target(name, ip, port=9100):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO vps_targets (name, ip, port) VALUES (?, ?, ?)", (name, ip, int(port)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error adding target: {e}")
        return False

def update_target(ip, enabled, notify):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE vps_targets SET enabled=?, notify=? WHERE ip=?", (1 if enabled else 0, 1 if notify else 0, ip))
    conn.commit()
    conn.close()

def delete_target(ip):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vps_targets WHERE ip=?", (ip,))
    conn.commit()
    conn.close()

def purge_database():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM status_history")
        c.execute("DELETE FROM notification_logs")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Purge failed: {e}")
        return False

def get_history_data(start_time=None, end_time=None):
    try:
        conn = get_db_connection()
        if not start_time:
            start_time = datetime.now() - timedelta(hours=3)
        
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
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT MAX(timestamp) FROM status_history")
        last_check = c.fetchone()[0]
        conn.close()

        if last_check:
            last_time = datetime.fromisoformat(last_check)
            gap = (datetime.now() - last_time).total_seconds()
            if gap > 120:
                st.toast("⚠️ Monitor heartbeat lost. Attempting restart...", icon="🚑")
                subprocess.Popen(["python3", "monitor.py"])
                return False
        return True
    except:
        return True

# Sidebar Logic
try:
    st.sidebar.image(LOGO_FILE, width='stretch')
except:
    st.sidebar.image(LOGO_URL, width='stretch')

st.sidebar.markdown("<h3 style='text-align: center; color: #FAFAFA;'>Aigentss Pulse Evolution</h3>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.header("Settings")

current_interval = int(get_config_value('check_interval', 60))
new_interval = st.sidebar.slider("Check Interval (seconds)", min_value=10, max_value=300, value=current_interval)
if new_interval != current_interval:
    set_config_value('check_interval', new_interval)
    st.rerun()

check_monitor_health()

st.title("Aigentss Pulse | Infrastructure Core Evolution")

tab1, tab2 = st.tabs(["📡 Live Dashboard", "⚙️ Configuration"])

if 'current_view_ip' not in st.session_state:
    st.session_state.current_view_ip = None
if 'current_view_name' not in st.session_state:
    st.session_state.current_view_name = None

with tab1:
    if st.session_state.current_view_ip:
        ip = st.session_state.current_view_ip
        name = st.session_state.current_view_name
        
        st.button("← Back to Overview", on_click=lambda: st.session_state.update(current_view_ip=None))
        st.subheader(f"🔍 Drill-Down: {name} ({ip})")
        
        # PRO Time Range Selector (Integrated into Detail)
        time_options = ["10m", "30m", "1h", "6h", "12h", "24h", "48h", "72h", "7d"]
        sel_range = st.select_slider("Select Filter Range", options=time_options, value="6h", key="detail_range")
        
        map_delta = {
            "10m": timedelta(minutes=10), "30m": timedelta(minutes=30), "1h": timedelta(hours=1),
            "6h": timedelta(hours=6), "12h": timedelta(hours=12), "24h": timedelta(hours=24),
            "48h": timedelta(hours=48), "72h": timedelta(hours=72), "7d": timedelta(days=7)
        }
        
        st_time = datetime.now() - map_delta[sel_range]
        conn = get_db_connection()
        df_detail = pd.read_sql_query("SELECT * FROM status_history WHERE ip=? AND timestamp >= ? ORDER BY timestamp ASC", conn, params=(ip, st_time))
        conn.close()
        
        if not df_detail.empty:
            df_detail['timestamp'] = pd.to_datetime(df_detail['timestamp'])
            latest = df_detail.iloc[-1]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Latency", f"{latest['latency']:.1f} ms")
            c2.metric("CPU", f"{latest['cpu']:.1f}%")
            c3.metric("RAM", f"{latest['ram']:.1f}%")
            c4.metric("Disk", f"{latest['disk']:.1f}%")
            
            st.markdown("### 📡 Latency History")
            st.line_chart(df_detail, x='timestamp', y='latency')
            st.markdown("### 💻 CPU & RAM Utilization")
            st.area_chart(df_detail, x='timestamp', y=['cpu', 'ram'])
        else:
            st.info("No historical data for this window.")
            
    else:
        st.subheader("Live Status [Modo Bypass]")
        df_status = get_latest_status()

        if not df_status.empty:
            cols = st.columns(4)
            for index, row in df_status.iterrows():
                col_idx = index % 4
                if index > 0 and index % 4 == 0:
                    cols = st.columns(4)
                
                with cols[col_idx]:
                    dot_color = "#00ff00" if row['status'] == 1 else "#ff0000"
                    card_class = "card-online" if row['status'] == 1 else "card-offline"
                    
                    st.markdown(f"""
                    <div class="metric-card {card_class}">
                        <div style="font-size: 1.1em; font-weight: bold; margin-bottom: 5px;">
                            <span class="status-dot" style="background-color: {dot_color};"></span>
                            {row['name']}
                        </div>
                        <div style="color: #888; font-size: 0.8em; margin-bottom: 5px;">{row['ip']}</div>
                        <div style="font-size: 1.8em; font-weight: bold; margin-bottom: 5px;">
                            {row['latency']:.1f} ms
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Triple Telemetry Bars
                    cpu, ram, disk = row.get('cpu', 0), row.get('ram', 0), row.get('disk', 0)
                    tc1, tc2, tc3 = st.columns(3)
                    with tc1:
                        st.caption(f"CPU: {cpu:.0f}%")
                        st.progress(min(int(cpu), 100)/100)
                    with tc2:
                        st.caption(f"RAM: {ram:.0f}%")
                        st.progress(min(int(ram), 100)/100)
                    with tc3:
                        st.caption(f"DISK: {disk:.0f}%")
                        st.progress(min(int(disk), 100)/100)
                    
                    if st.button("🔍 Details", key=f"d_{row['ip']}"):
                        st.session_state.current_view_ip = row['ip']
                        st.session_state.current_view_name = row['name']
                        st.rerun()
        else:
            st.warning("Pulse engine idle. Waiting for first check...")

    st.markdown("---")
    st.subheader("📊 Global Analytics Selector")
    
    ca1, ca2 = st.columns([3, 1])
    with ca1:
        range_pro = st.select_slider("Historical Range", options=["10m", "30m", "1h", "6h", "12h", "24h", "48h", "72h", "7d", "Calendar Audit"], value="1h")
    
    start_filter = None
    if range_pro == "Calendar Audit":
        with ca2:
            audit_date = st.date_input("Select Audit Date", datetime.now())
            start_filter = datetime.combine(audit_date, datetime.min.time())
            end_filter = datetime.combine(audit_date, datetime.max.time())
    else:
        map_delta = {
            "10m": timedelta(minutes=10), "30m": timedelta(minutes=30), "1h": timedelta(hours=1),
            "6h": timedelta(hours=6), "12h": timedelta(hours=12), "24h": timedelta(hours=24),
            "48h": timedelta(hours=48), "72h": timedelta(hours=72), "7d": timedelta(days=7)
        }
        start_filter = datetime.now() - map_delta[range_pro]
        end_filter = None

    df_hist = get_history_data(start_filter, end_filter)
    if not df_hist.empty:
        st.line_chart(df_hist, x="timestamp", y="latency", color="name")
    else:
        st.info("No data found for selected criteria.")

with tab2:
    st.header("Nucleus Configuration")
    
    with st.expander("🔐 SMTP Security Gateway"):
        s_user = st.text_input("Alert Email", value=get_config_value("email_user", ""))
        s_pass = st.text_input("Contraseña de Correo", type="password")
        if st.button("Save Securely"):
            if s_user and s_pass:
                set_config_value("email_user", s_user)
                enc = encrypt_val(s_pass)
                if enc: set_config_value("email_pass", enc)
                st.success("Credentials Encrypted.")
    
    st.markdown("---")
    st.subheader("⚙️ VPS Fleet Management")
    
    with st.expander("Add New Nucleus Target"):
        with st.form("fleet_form"):
            f_name = st.text_input("Server Title")
            f_ip = st.text_input("IP (Primary Key)")
            f_port = st.number_input("Node Exporter Port", value=9100)
            if st.form_submit_button("Engage Target"):
                if f_name and f_ip:
                    if add_target(f_name, f_ip, f_port):
                        st.success("Target Engaged.")
                        time.sleep(1)
                        st.rerun()

    df_f = get_targets()
    if not df_f.empty:
        for idx, row in df_f.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
            c1.write(f"**{row['name']}**")
            c2.write(row['ip'])
            
            en = c3.toggle("Enabled", value=bool(row['enabled']), key=f"toe_{row['ip']}")
            ni = c4.toggle("Alerts", value=bool(row['notify']), key=f"ton_{row['ip']}")
            
            if en != bool(row['enabled']) or ni != bool(row['notify']):
                update_target(row['ip'], en, ni)
                st.rerun()
                
            if c5.button("🗑️", key=f"k_v_{row['ip']}"):
                delete_target(row['ip'])
                st.rerun()

    st.markdown("---")
    st.subheader("🧹 System Maintenance")
    if st.button("⚠️ Purge Node Data", help="Wipes history & logs. Keeps configuration."):
        if purge_database():
            st.success("Nodes purged.")
            st.rerun()

    with st.expander("📜 Alert Audit Trail"):
        conn = get_db_connection()
        df_l = pd.read_sql_query("SELECT timestamp, recipient_email, vps_name, status FROM notification_logs ORDER BY timestamp DESC LIMIT 50", conn)
        conn.close()
        if not df_l.empty:
            st.dataframe(df_l, width='stretch')

st.markdown("---")
st.markdown("<div style='text-align: center; font-size: 0.8em; color: gray;'>© 2026 Aigentss Pulse Infinity Core.</div>", unsafe_allow_html=True)
