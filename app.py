import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import threading
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import monitor # Unified architecture: import the monitor module

# Configuration
DB_NAME = "aigentss_pulse.db"
LOGO_FILE = "Logo_1024.png"
LOGO_URL = "https://aigentss.com/wp-content/uploads/2023/11/logo-aigentss.png"
KEY_FILE = "secret.key"

st.set_page_config(page_title="Aigentss Pulse | Infrastructure Core", layout="wide", page_icon="📡")

# --- BACKGROUND MONITOR THREAD ---
if "monitor_started" not in st.session_state:
    # Start monitor in a dedicated background thread if not already running in this process
    # Note: Streamlit Cloud might restart the script, so we use a singleton-like check
    def run_monitor():
        monitor.master_loop()
    
    thread = threading.Thread(target=run_monitor, daemon=True)
    thread.start()
    st.session_state.monitor_started = True

# --- CSS & THEME ---
st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E1E; padding: 20px; border-radius: 10px; border: 1px solid #333;
        text-align: center; margin-bottom: 20px; color: white; border-left: 5px solid #00ff00;
    }
    .card-offline { border-left: 5px solid #ff0000; }
    .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def get_db_connection():
    return sqlite3.connect(DB_NAME)

def load_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f: return f.read()
    return None

def encrypt_val(val):
    key = load_key()
    if not key: return None
    return Fernet(key).encrypt(val.encode()).decode()

def get_latest_status():
    try:
        conn = get_db_connection()
        query = """
        SELECT sh.* FROM status_history sh
        INNER JOIN (SELECT ip, MAX(timestamp) as MaxTime FROM status_history GROUP BY ip) gsh
        ON sh.ip = gsh.ip AND sh.timestamp = gsh.MaxTime
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except: return pd.DataFrame()

def get_config_val(key, default):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key=?", (key,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else default
    except: return default

def set_config_val(key, val):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit(); conn.close()

# --- SIDEBAR & NAV ---
try:
    st.sidebar.image(LOGO_FILE, width='stretch')
except:
    st.sidebar.image(LOGO_URL, width='stretch')
st.sidebar.title("Pulse Evolution")
st.sidebar.markdown("---")
interval = int(get_config_val('check_interval', 60))
new_interval = st.sidebar.slider("Check Interval (s)", 10, 300, interval)
if new_interval != interval:
    set_config_val('check_interval', new_interval)
    st.rerun()

# --- MAIN UI ---
st.title("Aigentss Pulse | Infrastructure Core")
tab1, tab2 = st.tabs(["📡 Live Dashboard", "⚙️ Configuration"])

with tab1:
    # 1. Historical Analytics & Filters (Pro Slider & Calendar)
    st.subheader("📊 Analytical Intelligence")
    ca1, ca2 = st.columns([3, 1])
    with ca1:
        range_options = ["10m", "30m", "1h", "6h", "12h", "24h", "48h", "7d", "Calendar Audit"]
        sel_range = st.select_slider("Time Range Selector", options=range_options, value="1h")
    
    start_filter = None
    if sel_range == "Calendar Audit":
        with ca2:
            audit_date = st.date_input("Audit Date", datetime.now())
            start_filter = datetime.combine(audit_date, datetime.min.time())
            end_filter = datetime.combine(audit_date, datetime.max.time())
    else:
        map_delta = {"10m": 10, "30m": 30, "1h": 60, "6h": 360, "12h": 720, "24h": 1440, "48h": 2880, "7d": 10080}
        start_filter = datetime.now() - timedelta(minutes=map_delta.get(sel_range, 60))
        end_filter = None

    # Line Chart
    try:
        conn = get_db_connection()
        h_query = "SELECT name, latency, timestamp FROM status_history WHERE timestamp >= ?"
        h_df = pd.read_sql_query(h_query, conn, params=(start_filter,))
        conn.close()
        if not h_df.empty:
            h_df['timestamp'] = pd.to_datetime(h_df['timestamp'])
            st.line_chart(h_df, x="timestamp", y="latency", color="name")
    except: st.info("Initializing historical engine...")

    st.markdown("---")
    
    # 2. Live Status Cards (Modo Bypass & Triple Telemetry)
    st.subheader("📡 Real-Time Fleet Status")
    df_status = get_latest_status()
    if not df_status.empty:
        cols = st.columns(4)
        for idx, row in df_status.iterrows():
            with cols[idx % 4]:
                is_up = row['status'] == 1
                status_label = "Modo Bypass" if is_up else "OFFLINE"
                dot_color = "#00ff00" if is_up else "#ff0000"
                card_style = "" if is_up else "card-offline"
                
                st.markdown(f"""
                <div class="metric-card {card_style}">
                    <div style="font-size: 1.2em; font-weight: bold;">
                        <span class="status-dot" style="background-color: {dot_color};"></span>{row['name']}
                    </div>
                    <div style="color: #888; font-size: 0.8em; margin: 5px 0;">{row['ip']}</div>
                    <div style="font-size: 1.5em; font-weight: bold;">{row['latency']:.1f} ms</div>
                    <div style="color: {dot_color}; font-size: 0.9em; font-weight: bold; margin-top:5px;">{status_label}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Triple Telemetry Bars
                t1, t2, t3 = st.columns(3)
                t1.caption(f"CPU {row['cpu']:.0f}%"); t1.progress(min(int(row['cpu']), 100)/100)
                t2.caption(f"RAM {row['ram']:.0f}%"); t2.progress(min(int(row['ram']), 100)/100)
                t3.caption(f"DISK {row['disk']:.0f}%"); t3.progress(min(int(row['disk']), 100)/100)
    else:
        st.warning("Awaiting first telemetry pulse...")

with tab2:
    st.header("Nucleus Configuration")
    
    # Auth Section
    with st.expander("🔐 Alertas & Seguridad"):
        s_user = st.text_input("Correo de Monitoreo", value=get_config_val("email_user", ""))
        s_pass = st.text_input("Contraseña de Correo", type="password")
        if st.button("Guardar Credenciales"):
            if s_user and s_pass:
                set_config_val("email_user", s_user)
                enc = encrypt_val(s_pass)
                if enc: set_config_val("email_pass", enc)
                st.success("Configuración de correo guardada.")
    
    # VPS Management
    st.subheader("🖥️ Gestión de Servidores")
    with st.form("add_vps"):
        f1, f2 = st.columns(2)
        n_name = f1.text_input("Nombre del Servidor")
        n_ip = f2.text_input("Dirección IP")
        if st.form_submit_button("Añadir a la Flota"):
            if n_name and n_ip:
                conn = get_db_connection(); c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO vps_targets (name, ip, port) VALUES (?, ?, 9100)", (n_name, n_ip))
                conn.commit(); conn.close()
                st.rerun()

    # List
    try:
        conn = get_db_connection()
        targets = pd.read_sql_query("SELECT ip, name, enabled, notify FROM vps_targets", conn)
        conn.close()
        for _, r in targets.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(f"**{r['name']}** ({r['ip']})")
            en = c2.toggle("Activo", value=bool(r['enabled']), key=f"e_{r['ip']}")
            ni = c3.toggle("Alertas", value=bool(r['notify']), key=f"n_{r['ip']}")
            if c4.button("🗑️", key=f"d_{r['ip']}"):
                conn = get_db_connection(); c = conn.cursor()
                c.execute("DELETE FROM vps_targets WHERE ip=?", (r['ip'],))
                conn.commit(); conn.close(); st.rerun()
            # Update toggles
            if en != bool(r['enabled']) or ni != bool(r['notify']):
                conn = get_db_connection(); c = conn.cursor()
                c.execute("UPDATE vps_targets SET enabled=?, notify=? WHERE ip=?", (int(en), int(ni), r['ip']))
                conn.commit(); conn.close()
    except: pass

st.markdown("---")
st.markdown("<div style='text-align: center; color: #666;'>© 2026 Aigentss Pulse Infinity Core.</div>", unsafe_allow_html=True)
