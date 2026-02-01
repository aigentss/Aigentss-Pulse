import streamlit as st
import sqlite3
import pandas as pd
import time
from datetime import datetime, timedelta

# Configuration
DB_NAME = "aigentss_pulse.db"
LOGO_FILE = "Logo_1024.png"
LOGO_URL = "https://aigentss.com/wp-content/uploads/2023/11/logo-aigentss.png"

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
             df['port'] = 22 # Default for display if old schema using app before restart
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

def get_history_data():
    try:
        conn = get_db_connection()
        since = datetime.now() - timedelta(hours=24)
        query = "SELECT name, latency, timestamp FROM status_history WHERE timestamp > ?"
        df = pd.read_sql_query(query, conn, params=(since,))
        conn.close()
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except:
        return pd.DataFrame()

# Sidebar Styling
try:
    st.sidebar.image(LOGO_FILE, use_column_width=True)
except:
    st.sidebar.image(LOGO_URL, use_column_width=True)

st.sidebar.markdown("<h3 style='text-align: center; color: #FAFAFA;'>Aigentss Pulse</h3>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.header("Settings")

# Interval Setting
current_interval = int(get_config_value('check_interval', 60))
new_interval = st.sidebar.slider("Check Interval (seconds)", min_value=10, max_value=300, value=current_interval)
if new_interval != current_interval:
    set_config_value('check_interval', new_interval)
    st.sidebar.success(f"Interval updated to {new_interval}s")
    time.sleep(1)
    st.rerun()

# Main Title
st.title("Aigentss Pulse | Infrastructure Core")

# Tabs for Dashboard and Configuration
tab1, tab2 = st.tabs(["📡 Live Dashboard", "⚙️ Configuration"])

with tab1:
    # Live Status
    st.subheader("Live Status")
    df_status = get_latest_status()
    
    # Filter only enabled targets from the status view if needed, 
    # but status history might contain old data. 
    # Ideally we join with vps_targets to only show active ones, or just show what's in history (last check).
    # Improved query to filter enabled could be better, but let's stick to showing latest gathered data.
    
    if not df_status.empty:
        cols = st.columns(4)
        for index, row in df_status.iterrows():
            col_idx = index % 4
            if index > 0 and index % 4 == 0:
                cols = st.columns(4)
            
            with cols[col_idx]:
                # Determine Status Color
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

    # Latency History
    st.subheader("Latency History (Last 24 Hours)")
    df_history = get_history_data()
    if not df_history.empty:
        st.line_chart(df_history, x="timestamp", y="latency", color="name")
    else:
        st.info("Gathering historical metrics...")
        
    if st.button("Refresh Dashboard"):
        st.rerun()

with tab2:
    st.header("System Configuration")
    
    # Global Notification
    st.subheader("🔔 Global Notification Settings")
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
