import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import json
import threading
import io
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import monitor

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Aigentss Pulse | Infrastructure Core",
    layout="wide",
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- INITIALIZATION ---
monitor.start_monitor_thread()
DB_NAME = "aigentss_pulse.db"

# --- HELPERS FOR CONFIG ---
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

def save_config(key, val):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()

# --- THEME MANAGEMENT ---
# Load theme preference (persistence via DB)
theme_pref = get_config_val('theme_mode', "Dark (Infinity)")
is_dark = theme_pref == "Dark (Infinity)"

# --- DEFINING THEME CONSTANTS ---
if is_dark:
    # "Gris Elegante" / "Sofisticado"
    # Surfaces: #1E1E1E (Dark Grey), Text: #E0E0E0 (Light Grey)
    # Background: #121212 (Material Dark default recommendation)
    bg_color = "#121212"
    text_color = "#E0E0E0"
    card_bg = "#1E1E1E"
    card_border = "1px solid rgba(255, 255, 255, 0.1)"
    shadow = "0 4px 30px rgba(0, 0, 0, 0.5)"
    status_off_color = "#E0E0E0"
else:
    # "Clásico Profesional"
    # Background: #F4F4F4 (Gris muy claro)
    # Text: #333333 (Gris oscuro)
    # Card: #FFFFFF (Blanco)
    bg_color = "#F4F4F4"
    text_color = "#333333"
    card_bg = "#FFFFFF"
    card_border = "1px solid #E0E0E0"
    shadow = "0 2px 10px rgba(0,0,0,0.1)"
    status_off_color = "white" # Red status badge needs white text

# --- CSS INJECTION ---
css = f"""
<style>
    /* Global App Background */
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
        font-family: 'Inter', sans-serif;
    }}
    
    /* Card Style - Glassmorphism & Neon */
    div.css-1r6slb0.e1tzin5v2, .stContainer {{
        background-color: {card_bg};
        border: {card_border};
        border-radius: 12px;
        box-shadow: {shadow};
        backdrop-filter: blur(5px);
        padding: 15px;
        transition: transform 0.2s;
    }}
    
    /* Metric Containers (Custom Class) */
    .vps-card {{
        background-color: {card_bg};
        padding: 20px;
        border-radius: 10px;
        border: {card_border};
        margin-bottom: 20px;
        box-shadow: {shadow};
        color: {text_color};
    }}
    
    .status-badge {{
        font-weight: bold;
        padding: 5px 10px;
        border-radius: 5px;
        color: black;
        text-transform: uppercase;
        font-size: 0.8rem;
    }}
    .status-up {{ background-color: #00ff00; box-shadow: 0 0 10px #00ff00; }}
    .status-down {{ background-color: #ff0000; box-shadow: 0 0 10px #ff0000; color: {status_off_color}; }}

    /* Custom Progress Bars */
    .stProgress > div > div > div > div {{
        background-color: #00ff00;
        background-image: linear-gradient(to right, #00ff00, #00cc00);
    }}
    
    /* Text corrections for Light/Dark Mode consistency */
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, .stText, .stRadio label {{
        color: {text_color} !important;
    }}
    
    /* Streamlit Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 10px;
    }}

    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        white-space: pre-wrap;
        background-color: {card_bg};
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
        color: {text_color};
    }}

    .stTabs [aria-selected="true"] {{
        background-color: {bg_color};
        border-bottom: 2px solid #00ff00;
    }}

</style>
"""
st.markdown(css, unsafe_allow_html=True)

# --- APP LAYOUT HEADER ---
st.title("📡 Aigentss Pulse | v2.0")

# --- HELPERS DATA ---
@st.cache_data(ttl=5) # Cache for 5s to keep UI fluid
def get_dashboard_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        # Get list of targets
        targets = pd.read_sql_query("SELECT name, ip, port, enabled FROM vps_targets WHERE enabled=1", conn)
        
        results = []
        for _, row in targets.iterrows():
            # Get latest status
            df_status = pd.read_sql_query(
                "SELECT status, latency, cpu, ram, disk, timestamp FROM status_history WHERE ip=? ORDER BY timestamp DESC LIMIT 1",
                conn, params=(row['ip'],)
            )
            data = {
                'name': row['name'],
                'ip': row['ip'],
                'status': 0, 'latency': 0.0, 'cpu': 0.0, 'ram': 0.0, 'disk': 0.0, 'last_seen': 'Never'
            }
            if not df_status.empty:
                r = df_status.iloc[0]
                data.update({
                    'status': r['status'],
                    'latency': r['latency'],
                    'cpu': r['cpu'], 'ram': r['ram'], 'disk': r['disk'],
                    'last_seen': r['timestamp']
                })
            results.append(data)
        conn.close()
        return results
    except Exception as e:
        return []

def get_historical_metrics(hours=24):
    try:
        conn = sqlite3.connect(DB_NAME)
        cutoff = datetime.now() - timedelta(hours=hours)
        df = pd.read_sql_query(
            "SELECT name, ip, latency, cpu, ram, disk, timestamp FROM status_history WHERE timestamp >= ? ORDER BY timestamp ASC",
            conn, params=(cutoff,)
        )
        conn.close()
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except:
        return pd.DataFrame()

def get_docker_snapshot(ip):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT json_data FROM docker_snapshot WHERE ip=?", (ip,))
        res = c.fetchone()
        conn.close()
        if res:
            return json.loads(res[0])
        return []
    except:
        return []

def load_config(key, default):
    return monitor.get_config_val(key, default)

def add_vps(name, ip, port=9100):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR IGNORE INTO vps_targets (name, ip, port) VALUES (?, ?, ?)", (name, ip, port))
    conn.commit()
    conn.close()

def remove_vps(ip):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM vps_targets WHERE ip=?", (ip,))
    conn.commit()
    conn.close()

def encrypt_secret(val):
    key = monitor.load_or_create_key()
    f = Fernet(key)
    return f.encrypt(val.encode()).decode()

# Tabs
tab_live, tab_graphs, tab_config, tab_history = st.tabs([
    "🚀 Status Live", 
    "📈 Graficas (Analytics)", 
    "⚙️ Nucleus Config", 
    "📜 History & Export"
])

# --- TAB 1: LIVE STATUS ---
with tab_live:
    st.markdown("### 🧬 Infrastructure Vital Signs")
    
    # Auto-refresh mechanism
    if st.checkbox("Auto-refresh (10s)", value=True):
        time.sleep(1)
        st.rerun()

    data = get_dashboard_data()
    
    if not data:
        st.warning("No VPS targets configured or monitoring initializing...")
    else:
        # Create grid
        cols = st.columns(3)
        for i, vps in enumerate(data):
            col = cols[i % 3]
            with col:
                # Bypass Mode visual
                border_color = "#00ff00" if vps['status'] == 1 else "#ff0000"
                glow = f"box-shadow: 0px 0px 15px {border_color};" if is_dark else f"box-shadow: 0px 0px 5px {border_color};"
                
                with st.container(border=True):
                    # Header
                    st.markdown(f"#### {vps['name']}")
                    st.markdown(f"`{vps['ip']}`")
                    
                    # Connection Status
                    if vps['status'] == 1:
                        st.markdown(f"<span class='status-badge status-up'>● UP [Bypass]</span>", unsafe_allow_html=True)
                        st.caption(f"Latency: {vps['latency']:.1f}ms")
                    else:
                        st.markdown(f"<span class='status-badge status-down'>● DOWN</span>", unsafe_allow_html=True)
                        st.caption("Connection Failed")
                        
                    st.markdown("---")
                    
                    # Telemetry Triple
                    st.text("CPU Usage")
                    st.progress(min(int(vps['cpu']), 100))
                    
                    st.text("RAM Usage")
                    st.progress(min(int(vps['ram']), 100))
                    
                    st.text("Disk Usage")
                    st.progress(min(int(vps['disk']), 100))
                    
                    st.caption(f"Updated: {vps['last_seen']}")

                    # Drill Down Button
                    with st.expander("🐳 Docker Drill Down"):
                        docker_data = get_docker_snapshot(vps['ip'])
                        if docker_data:
                            # Separate by type
                            apps = [d for d in docker_data if d['type'] == 'app']
                            dbs = [d for d in docker_data if d['type'] == 'db']
                            
                            if apps:
                                st.markdown("**Applications**")
                                for c in apps:
                                    mem_mb = c['memory_bytes'] / 1024 / 1024
                                    st.markdown(f"- **{c['name']}**: {c['cpu_seconds']:.2f}s CPU | {mem_mb:.1f} MB")
                            
                            if dbs:
                                st.markdown("**Databases**")
                                for c in dbs:
                                    mem_mb = c['memory_bytes'] / 1024 / 1024
                                    st.markdown(f"- 🗄️ **{c['name']}**: {c['cpu_seconds']:.2f}s CPU | {mem_mb:.1f} MB")
                        else:
                            st.info("No container metrics available.")

# --- TAB 2: GRAFICAS ---
with tab_graphs:
    st.header("📈 Rendimiento Histórico (24h)")
    
    df_hist = get_historical_metrics(hours=24)
    if not df_hist.empty:
        # User Selection for Filter
        all_hosts = df_hist['name'].unique()
        selected_hosts = st.multiselect("Filtrar VPS:", all_hosts, default=all_hosts)
        
        if selected_hosts:
            df_filtered = df_hist[df_hist['name'].isin(selected_hosts)]
            
            st.subheader("⏱️ Latencia (ms)")
            st.line_chart(df_filtered, x='timestamp', y='latency', color='name')
            
            st.subheader("💻 Uso de CPU (%)")
            st.line_chart(df_filtered, x='timestamp', y='cpu', color='name')
            
            st.subheader("🧠 Uso de RAM (%)")
            st.line_chart(df_filtered, x='timestamp', y='ram', color='name')
            
            st.subheader("💾 Uso de Disco (%)")
            st.line_chart(df_filtered, x='timestamp', y='disk', color='name')
        else:
            st.info("Selecciona al menos un VPS para ver las gráficas.")
    else:
        st.info("Aún no hay datos históricos suficientes para graficar.")

# --- TAB 3: NUCLEUS CONFIG ---
with tab_config:
    st.header("🛠️ Nucleus Control Panel")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Global Settings")
        
        # Theme Toggle (Moved from Sidebar)
        st.markdown("#### Aesthetic Mode")
        current_theme = get_config_val('theme_mode', "Dark (Infinity)")
        selected_theme = st.radio(
            "Selecciona el tema de la interfaz:",
            ["Dark (Infinity)", "Light (Daywalker)"],
            index=0 if current_theme == "Dark (Infinity)" else 1,
            horizontal=True
        )
        
        if selected_theme != current_theme:
            save_config('theme_mode', selected_theme)
            st.success("Theme updated! Reloading...")
            time.sleep(1)
            st.rerun()

        # Sampling Rate
        st.markdown("---")
        st.markdown("#### Performance")
        current_interval = int(load_config('check_interval', 60))
        new_interval = st.slider("Sampling Frequency (s)", 10, 300, current_interval)
        if new_interval != current_interval:
            save_config('check_interval', new_interval)
            st.success("Interval updated via WAL!")

        # File Name
        export_name = st.text_input("Export Filename Template", value="pulse_sampling_report_[timestamp].csv")
        save_config('export_filename', export_name)

    with c2:
        st.subheader("Alerts (SMTP)")
        email_user = st.text_input("SMTP Email (Gmail)", value=load_config('email_user', ''))
        email_pass = st.text_input("SMTP Password", type="password")
        
        if st.button("Save Credentials"):
            save_config('email_user', email_user)
            if email_pass:
                save_config('email_pass', encrypt_secret(email_pass))
            st.success("Credentials Encrypted & Saved.")
    
    st.markdown("---")
    st.subheader("VPS Management")
    
    # Add VPS
    with st.form("add_vps"):
        c_name, c_ip = st.columns(2)
        new_name = c_name.text_input("VPS Name")
        new_ip = c_ip.text_input("IP Address")
        submitted = st.form_submit_button("Add Node")
        if submitted and new_name and new_ip:
            add_vps(new_name, new_ip)
            st.success(f"Added {new_name}")
            st.rerun()
            
    # List/Remove VPS
    st.markdown("##### Current Nodes")
    stored_vps = get_dashboard_data()
    for v in stored_vps:
        c_info, c_del = st.columns([4, 1])
        c_info.text(f"{v['name']} - {v['ip']}")
        if c_del.button("🗑️", key=f"del_{v['ip']}"):
            remove_vps(v['ip'])
            st.rerun()

# --- TAB 4: HISTORY ---
with tab_history:
    st.subheader("📊 Historical Data Export")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM status_history ORDER BY timestamp DESC LIMIT 1000", conn)
    conn.close()
    
    st.dataframe(df)
    
    # Dynamic Filename
    filename_template = load_config('export_filename', "pulse_sampling_report_[timestamp].csv")
    fname = filename_template.replace("[timestamp]", datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Full Report (CSV)",
        data=csv,
        file_name=fname,
        mime='text/csv',
    )
