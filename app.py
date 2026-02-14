"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

Entry point for the Streamlit Dashboard.

ARCHITECTURAL DECISION:
- Uses Streamlit for rapid UI development with 'Infinity' (Dark) and 'Daywalker' (Light) themes.
- Implements direct DB polling for real-time status to avoid complex websocket infrastructure.
- Forces Altair charts with [0, 100] Y-axis domain to prevent visual distortion from outliers.
"""

import streamlit as st
import os
import time
from datetime import datetime, timedelta
import pandas as pd
import logging
import json
import altair as alt

# Import our modules
import db
import monitor
import notification
import report
from prometheus_metrics import scrape_vps


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== PAGE CONFIGURATION ==========

st.set_page_config(
    page_title="Aigents Pulse v3.1 (Spectre+)",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ========== THEME SYSTEM ==========

def apply_theme(theme_name: str):
    """Apply custom CSS for the selected theme."""
    
    # --- VISUAL SETTINGS (GLOBAL) ---
    # We inject this into the sidebar here so it's available everywhere
    with st.sidebar.expander("🎨 Visual Settings", expanded=False):
        st.session_state['show_points'] = st.checkbox("Show Data Points", value=False)
        st.session_state['line_stroke'] = st.slider("Line Thickness", 0.5, 5.0, 1.5, 0.5)
        st.session_state['curve_type'] = st.selectbox("Line Curve", ["monotone", "linear", "step", "basis"], index=0)

    if theme_name == "Infinity":
        # Dark theme with neon accents
        st.markdown("""
        <style>
            .stApp {
                background-color: #0E1117;
                color: #ffffff;
            }
            
            .status-card-up {
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                border: 2px solid #00ff00;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
                backdrop-filter: blur(8px);
            }
            
            .status-card-down {
                background: linear-gradient(135deg, #2e1a1a 0%, #3e1621 100%);
                border: 2px solid #ff0000;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 0 20px rgba(255, 0, 0, 0.3);
                backdrop-filter: blur(8px);
            }
            
            .metric-badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 16px;
                font-size: 12px;
                font-weight: bold;
                margin: 4px;
            }
            
            .badge-success {
                background-color: rgba(0, 255, 0, 0.2);
                color: #00ff00;
                border: 1px solid #00ff00;
            }
            
            .badge-danger {
                background-color: rgba(255, 0, 0, 0.2);
                color: #ff0000;
                border: 1px solid #ff0000;
            }
            
            .stProgress > div > div > div {
                background: linear-gradient(90deg, #00ff00, #00d4ff);
            }
            
            h1, h2, h3 {
                color: #00ff00;
                text-shadow: 0 0 10px rgba(0, 255, 0, 0.5);
            }
            
            .status-card-sec {
                background: linear-gradient(135deg, #16213e 0%, #0f3460 100%);
                border: 1px solid #00d4ff;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 0 15px rgba(0, 212, 255, 0.2);
            }
            
            .port-metric {
                background: rgba(255, 255, 255, 0.05);
                padding: 10px;
                border-radius: 8px;
                margin-top: 5px;
                font-family: monospace;
            }
            
            .footer {
                position: fixed;
                left: 0;
                bottom: 0;
                width: 100%;
                background-color: transparent;
                color: rgba(255,255,255,0.5);
                text-align: center;
                padding: 10px;
                font-size: 12px;
                z-index: 100;
            }
        </style>
        """, unsafe_allow_html=True)
    
    else:  # Daywalker (Light theme)
        st.markdown("""
        <style>
            .stApp {
                background-color: #F4F4F4;
                color: #333333;
            }
            
            .status-card-up {
                background: linear-gradient(135deg, #ffffff 0%, #f0f0f0 100%);
                border: 2px solid #28a745;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            }
            
            .status-card-down {
                background: linear-gradient(135deg, #fff5f5 0%, #ffe0e0 100%);
                border: 2px solid #dc3545;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 2px 10px rgba(220, 53, 69, 0.2);
            }
            
            .metric-badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 16px;
                font-size: 12px;
                font-weight: bold;
                margin: 4px;
            }
            
            .badge-success {
                background-color: #28a745;
                color: white;
            }
            
            .badge-danger {
                background-color: #dc3545;
                color: white;
            }
            
            h1, h2, h3 {
                color: #2c3e50;
            }
            
            .status-card-sec {
                background: #ffffff;
                border: 1px solid #00d4ff;
                border-radius: 12px;
                padding: 20px;
                margin: 10px 0;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
            }
            
            .port-metric {
                background: #f8f9fa;
                padding: 10px;
                border-radius: 8px;
                margin-top: 5px;
            }
            
            .footer {
                position: fixed;
                left: 0;
                bottom: 0;
                width: 100%;
                background-color: transparent;
                color: rgba(0,0,0,0.5);
                text-align: center;
                padding: 10px;
                font-size: 12px;
                z-index: 100;
            }
        </style>
        """, unsafe_allow_html=True)


# ========== DAEMON AUTO-START ==========

@st.cache_resource
def get_monitor_daemon():
    """Initialize and start the monitoring daemon (singleton)."""
    logger.info("Initializing monitor daemon...")
    daemon = monitor.get_daemon()
    daemon.start()
    try: report.init_scheduler()
    except Exception as e: logger.error(f"Report scheduler init failed: {e}")
    return daemon


# ========== HELPER FUNCTIONS ==========

def create_history_chart(data, y_col, title, color_hex):
    """Create a sparkline-style history chart using Altair."""
    if data.empty:
        return st.info("No history data available")

    # Convert timestamp to datetime for Altair if not already
    if not pd.api.types.is_datetime64_any_dtype(data['timestamp']):
            data['timestamp_dt'] = pd.to_datetime(data['timestamp'], unit='s')
    else:
            data['timestamp_dt'] = data['timestamp']

    chart = alt.Chart(data).mark_line(
        point=st.session_state.get('show_points', False),
        strokeWidth=st.session_state.get('line_stroke', 1.5),
        interpolate=st.session_state.get('curve_type', 'monotone'),
        color=color_hex
    ).encode(
        x=alt.X('timestamp_dt:T', axis=alt.Axis(title=None, format='%H:%M')),
        y=alt.Y(y_col, axis=alt.Axis(title=title), scale=alt.Scale(domain=[0, 100])),
        tooltip=['timestamp_dt', alt.Tooltip(y_col, title=title, format='.1f')]
    ).properties(
        height=250
    ).interactive()

    st.altair_chart(chart, use_container_width=True)


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp to human-readable string."""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def get_status_badge(status: str) -> str:
    """Generate HTML badge for status."""
    if status == 'UP':
        return '<span class="metric-badge badge-success">✅ UP</span>'
    else:
        return '<span class="metric-badge badge-danger">❌ DOWN</span>'


# ========== MAIN APP ==========

def main():
    """Main application entry point."""
    
    # Load theme preference
    theme = db.get_config('ui_theme', 'Infinity')
    apply_theme(theme)
    
    # Auto-start daemon
    daemon = get_monitor_daemon()
    
    # Header - NO EMOJIS
    st.title("Aigents Pulse v3.1")
    st.caption("Spectre+ Branch - Infrastructure Observability Platform")
    
    # Navigation tabs - NO EMOJIS
    tab_sec, tab1, tab2, tab3, tab4, tab_debug = st.tabs([
        "Security",
        "Status Live",
        "Analytics",
        "Nucleus Config",
        "History & Export",
        "🔍 Debug/Raw Metrics"
    ])

    # ==================== TAB 0: SECURITY ====================
    with tab_sec:
        st.subheader("🔐 Global Security Audit")
        
        vps_list = db.list_vps(enabled_only=True)
        if not vps_list:
            st.info("No VPS to monitor. Configure them in Nucleus Config.")
        else:
            sec_cols = st.columns(3)
            for idx, vps in enumerate(vps_list):
                with sec_cols[idx % 3]:
                    st.markdown(render_security_card(vps), unsafe_allow_html=True)
                    if st.button(f"🛡️ Security Detail", key=f"sec_btn_{vps['ip']}", use_container_width=True):
                        st.session_state['view_sec_ip'] = vps['ip']
                        st.session_state['view_sec_name'] = vps['name']
            
            if 'view_sec_ip' in st.session_state:
                ip_sec = st.session_state['view_sec_ip']
                name_sec = st.session_state['view_sec_name']
                st.divider()
                st.subheader(f"Security Intelligence: {name_sec}")
                
                if st.button("Close Security View"):
                    del st.session_state['view_sec_ip']
                    st.rerun()
                
                latest_sec = db.get_latest_security_snapshot(ip_sec)
                if not latest_sec:
                    st.warning("No security snapshots found for this node.")
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("**Hardening & Services**")
                        st.json(latest_sec.get('ssh_hardening', {}))
                        st.write(f"**UFW Firewall:** `{latest_sec.get('firewall', 'UNKNOWN')}`")
                        st.write(f"**Fail2Ban:** `{latest_sec.get('fail2ban', 'UNKNOWN')}`")
                    
                    with c2:
                        st.write("**Active Port Throughput**")
                        active_ports = latest_sec.get('active_ports', [])
                        if active_ports:
                            df_ports = pd.DataFrame(active_ports)
                            st.bar_chart(df_ports.set_index('port')[['rx_kbps', 'tx_kbps']])
                        else:
                            st.info("No active port traffic detected.")
                    
                    st.write("**Full Security Snapshot (Raw JSON)**")
                    st.json(latest_sec)
    
    # ==================== TAB 1: STATUS LIVE ====================
    with tab1:
        st.subheader("Real-Time VPS Status")
        
        col_refresh, col_daemon = st.columns([3, 1])
        with col_refresh:
            if st.button("Refresh Now", use_container_width=True): st.rerun()
        with col_daemon:
            daemon_status = daemon.get_status()
            if daemon_status['running']: st.success(f"✓ Daemon Active ({daemon_status['interval']}s)")
            else: st.error("✗ Daemon Stopped")
        
        vps_list = db.list_vps(enabled_only=True)
        
        if not vps_list:
            st.warning("No VPS configured. Go to **Nucleus Config** to add VPS.")
        else:
            cols_per_row = 3
            rows = [vps_list[i:i + cols_per_row] for i in range(0, len(vps_list), cols_per_row)]
            
            for row in rows:
                cols = st.columns(cols_per_row)
                for col, vps in zip(cols, row):
                    with col:
                        st.markdown(render_vps_card(vps), unsafe_allow_html=True)
                        if st.button(f"🔍 Docker Dashboard", key=f"det_{vps['ip']}", use_container_width=True):
                            st.session_state['selected_vps_ip'] = vps['ip']
                            st.session_state['selected_vps_name'] = vps['name']
            
            # Docker Detail Dashboard (Overlay-like section)
            if 'selected_vps_ip' in st.session_state:
                ip = st.session_state['selected_vps_ip']
                name = st.session_state['selected_vps_name']
                st.divider()
                st.subheader(f"Docker Performance Dashboard: {name}")
                
                # Close button
                if st.button("Close Dashboard", key="close_docker"):
                    del st.session_state['selected_vps_ip']
                    st.rerun()
                
                # Metrics and history
                docker_hist = db.get_docker_history(ip, limit=50)
                if not docker_hist:
                    st.info("No Docker historical data found for this VPS.")
                else:
                    # Current Containers
                    latest = json.loads(docker_hist[0]['containers_json'])
                    
                    # Prepare df_docker for charts and table
                    hist_data = []
                    for h in docker_hist:
                        ts = format_timestamp(h['timestamp'])
                        conts = json.loads(h['containers_json'])
                        for c in conts:
                            hist_data.append({
                                "Time": ts,
                                "timestamp": h['timestamp'], # Add raw TS for Altair
                                "Container": c['name'],
                                "Status": c.get('status', 'RUNNING'),
                                "CPU %": c.get('cpu_percent', 0.0),
                                "Memory GB": round((c.get('memory_mb', 0.0) / 1024.0), 3)
                            })
                    df_docker = pd.DataFrame(hist_data)
                    # Convert Time to datetime for Altair
                    df_docker['Time_dt'] = pd.to_datetime(df_docker['timestamp'], unit='s')

                    # ... (rest of processing)

                    # Resource Summaries (Top Consumers)
                    if not df_docker.empty:
                        last_ts = df_docker['Time'].iloc[0]
                        current_snap = df_docker[df_docker['Time'] == last_ts]
                        
                        sum_cols = st.columns(2)
                        with sum_cols[0]:
                            st.write("**Top CPU Containers**")
                            top_cpu = current_snap.sort_values('CPU %', ascending=False).head(5)
                            st.bar_chart(top_cpu.set_index('Container')['CPU %'])
                        
                        with sum_cols[1]:
                            st.write("**Top RAM Containers**")
                            top_ram = current_snap.sort_values('Memory GB', ascending=False).head(5)
                            st.bar_chart(top_ram.set_index('Container')['Memory GB'])
                    
                    st.divider()
                    
                    # Live Containers with Sparklines
                    st.write(f"**Live Containers:** {len(latest)}")
                    live_cols = st.columns(4)
                    for idx, container in enumerate(latest):
                        c_name = container['name']
                        cpu_val = container.get('cpu_percent') or 0.0
                        mem_gb = (container.get('memory_mb') or 0.0) / 1024.0
                        
                        with live_cols[idx % 4]:
                            # Container card
                            with st.container(border=True):
                                cpu_fmt = f"{cpu_val:.2f}" if cpu_val < 1.0 else f"{cpu_val:.1f}"
                                st.metric(c_name[:20], f"{cpu_fmt}% CPU", f"{mem_gb:.3f} GB")
                                
                                # Mini sparkline for this container
                                if not df_docker.empty:
                                    c_hist = df_docker[df_docker['Container'] == c_name].tail(10)
                                    if not c_hist.empty:
                                        # Use Altair for sparklines too to match style? 
                                        # st.line_chart is simple but doesn't support our styling constraints easily.
                                        # Let's upgrade this to Altair sparkline
                                        
                                        spark = alt.Chart(c_hist).mark_line(
                                            point=False, # Sparklines usually no points
                                            strokeWidth=st.session_state.get('line_stroke', 1.5),
                                            interpolate=st.session_state.get('curve_type', 'monotone'),
                                            color='#00d4ff'
                                        ).encode(
                                            x=alt.X('Time:T', axis=None),
                                            y=alt.Y('CPU %:Q', axis=None, scale=alt.Scale(domain=[0, 100])),
                                            tooltip=['Time', 'CPU %']
                                        ).properties(
                                            height=60,
                                            width='container'
                                        )
                                        st.altair_chart(spark, use_container_width=True)

                    st.divider()
                    
                    # Global VPS Resource Summary
                    st.subheader("Global Docker vs System Summary")
                    view_vps_ip = ip # Use the 'ip' variable from the outer scope
                    vps_latest = db.get_latest_status(view_vps_ip)
                    if vps_latest and not df_docker.empty:
                        last_ts = df_docker['Time'].iloc[0]
                        snap = df_docker[df_docker['Time'] == last_ts]
                        # Calculate Docker vs System ratios
                        total_docker_cpu = snap['CPU %'].sum()
                        total_docker_ram_gb = snap['Memory GB'].sum()
                        
                        sys_cpu = vps_latest.get('cpu_percent', 0.0) or 0.0
                        sys_ram_pct = vps_latest.get('ram_percent', 0.0) or 1.0 # Avoid div by zero
                        
                        # Heuristic to estimate system RAM in info message
                        # If Docker uses X GB and Sys is Y%, then Total is roughly X / (Y/100)
                        # But that's only if Docker is the ONLY thing using RAM.
                        
                        sum_data = {
                            "Metric": ["CPU Usage (%)", "RAM Usage (GB)"],
                            "Docker Total": [f"{total_docker_cpu:.1f}%", f"{total_docker_ram_gb:.3f} GB"],
                            "System Global": [f"{sys_cpu:.1f}%", f"{sys_ram_pct:.1f}% (Host)"]
                        }
                        st.table(pd.DataFrame(sum_data))
                        
                        # Warning if Docker usage looks impossible
                        if total_docker_cpu > 1000 or total_docker_ram_gb > 512:
                            st.warning("⚠️ Detected anomalous Docker metrics. Normalization in progress...")
                        else:
                            st.info(f"💡 Docker containers are utilizing approximately **{total_docker_cpu:.1f}%** of the current CPU load.")
                    
                    # Historical Data Table
                    st.write("**Full History Log**")
                    st.dataframe(df_docker, use_container_width=True)
                    
                    # Export button specifically for Docker
                    csv_docker = df_docker.to_csv(index=False)
                    st.download_button(
                        "📥 Download Docker History CSV",
                        data=csv_docker,
                        file_name=f"docker_metrics_{name}_{ip}.csv",
                        mime="text/csv"
                    )

    # ==================== TAB 2: ANALYTICS ====================
    with tab2:
        st.subheader("Performance Analytics")
        col1, col2, col3 = st.columns(3)
        with col1:
            vps_list_all = db.list_vps()
            vps_options = {vps['name']: vps['ip'] for vps in vps_list_all}
            # Default to ALL VPS selected
            selected_vps = st.multiselect("Select VPS", options=list(vps_options.keys()), default=list(vps_options.keys()))
        with col2:
            # Default metric is Latency
            metric_type = st.selectbox("Metric Type", options=["Latency (ms)", "CPU %", "RAM %", "Disk %"], index=0)
        with col3:
            time_range = st.selectbox("Time Range", options=["Last 6 Hours", "Last 24 Hours", "Last 7 Days", "Last 30 Days"])
        
        hours_map = {"Last 6 Hours": 6, "Last 24 Hours": 24, "Last 7 Days": 24 * 7, "Last 30 Days": 24 * 30}
        start_time = int(time.time()) - (hours_map[time_range] * 3600)
        
        if selected_vps:
            chart_data = []
            for vps_name in selected_vps:
                history = db.get_history(vps_ip=vps_options[vps_name], start_time=start_time, limit=5000)
                for record in history:
                    val = record['latency_ms'] if metric_type == "Latency (ms)" else record['cpu_percent'] if metric_type == "CPU %" else record['ram_percent'] if metric_type == "RAM %" else record['disk_percent']
                    if val is not None: chart_data.append({'Time': datetime.fromtimestamp(record['timestamp']), 'VPS': vps_name, metric_type: val})
            
            if chart_data:
                df = pd.DataFrame(chart_data)
                
                # USE ALTAIR TO FORCE Y-AXIS SCALE
                if metric_type in ["CPU %", "RAM %", "Disk %"]:
                    # Force 0-100 scale for percentages
                    y_scale = alt.Scale(domain=[0, 100])
                    y_title = f"{metric_type} (Capacity)"
                else:
                    # Auto-scale for Latency but maybe cap it visually if huge?
                    # For now, let latency auto-scale but we cleaned the DB so it should be fine.
                    y_scale = alt.Scale(zero=True) # Ensure it starts at 0
                    y_title = metric_type

                # Create the chart
                chart = alt.Chart(df).mark_line(
                    point=st.session_state.get('show_points', False),
                    strokeWidth=st.session_state.get('line_stroke', 1.5),
                    interpolate=st.session_state.get('curve_type', 'monotone')
                ).encode(
                    x=alt.X('Time:T', title='Time'),
                    y=alt.Y(metric_type, title=y_title, scale=y_scale),
                    color=alt.Color('VPS:N', title='VPS Node'),
                    tooltip=['Time', 'VPS', alt.Tooltip(metric_type, format='.2f')]
                ).properties(
                    height=400
                ).interactive()

                st.altair_chart(chart, use_container_width=True)
                
                # Summary statistics with units
                st.subheader("📈 Summary Statistics")
                st.caption("🔹 CPU %, RAM %, and Disk % are expressed as percentages (0-100%). 📊 Latency is in milliseconds.")
                
                summary_cols = st.columns(len(selected_vps))
                
                for i, vps_name in enumerate(selected_vps):
                    with summary_cols[i]:
                        vps_data = df[df['VPS'] == vps_name][metric_type]
                        if not vps_data.empty:
                            # Add units based on metric type
                            if metric_type == "Latency (ms)":
                                unit = " ms"
                            else:
                                unit = "%"
                            
                            st.metric(
                                label=vps_name,
                                value=f"{vps_data.mean():.2f}{unit}",
                                delta=f"Max: {vps_data.max():.2f}{unit}"
                            )
            else: st.info("No data available for selected filters.")
        else: st.info("Select at least one VPS to view analytics.")
    
    # ==================== TAB 3: NUCLEUS CONFIG ====================
    with tab3:
        st.subheader("⚙️ System Configuration")
        
        col_theme, col_int = st.columns(2)
        with col_theme:
            st.write("**🎨 UI Theme**")
            current_theme = db.get_config('ui_theme', 'Infinity')
            new_theme = st.radio("Select Theme", options=["Infinity", "Daywalker"], index=0 if current_theme == "Infinity" else 1, horizontal=True)
            if new_theme != current_theme:
                db.set_config('ui_theme', new_theme)
                if st.button("🔄 Apply Theme"): st.rerun()
        
        with col_int:
            st.write("**🔧 Monitoring Settings**")
            cur_int = daemon.get_status()['interval']
            new_int = st.slider("Collection Interval (sec)", 10, 300, cur_int, 10)
            if st.button("💾 Save Interval"):
                daemon.set_interval(new_int); st.success(f"Updated to {new_int}s")

        st.divider()
        
        # SMTP Configuration
        st.subheader("📧 SMTP Configuration")
        st.info("⚠️ Credentials are encrypted using Fernet. Generate FERNET_KEY first.")
        
        smtp_server = st.text_input("SMTP Server", value=os.getenv("SMTP_SERVER", "smtp.gmail.com"))
        smtp_port = st.number_input("SMTP Port", value=int(os.getenv("SMTP_PORT", "587")))
        alert_email = st.text_input("Alert Recipient Email", value=os.getenv("ALERT_EMAIL", ""))
        
        if st.button("Test SMTP Connection"):
            st.info("Testing SMTP... (not implemented in UI)")
        
        st.divider()
        
        st.write("**🖥️ VPS Inventory Management**")
        with st.expander("➕ Add New VPS Node"):
            c1, c2 = st.columns(2)
            with c1:
                new_ip = st.text_input("IP Address")
                new_name = st.text_input("Friendly Name")
            with c2:
                new_port = st.number_input("Node Exporter", 9100)
                new_cadvisor = st.number_input("cAdvisor", 8080)
            if st.button("Save VPS Node"):
                if db.add_vps(new_ip, new_name, new_port, new_cadvisor): st.success("Added."); st.rerun()
                else: st.error("VPS already exists or invalid data")
        
        vps_inv = db.list_vps()
        if vps_inv:
            st.write(f"**Total VPS:** {len(vps_inv)}")
            st.write("**Hardware Configuration**")
            st.caption("Set maximum hardware capacity for each VPS to enable overshoot detection")
            
            for v in vps_inv:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    
                    with c1:
                        st.write(f"**{v['name']}** ({v['ip']})")
                        enable_key = f"enable_{v['ip']}"
                        is_enabled = st.checkbox("Active", v['enabled'] == 1, key=enable_key)
                        if is_enabled != (v['enabled'] == 1):
                            db.update_vps(v['ip'], enabled=is_enabled)
                    
                    with c2:
                        hw_cols = st.columns(3)
                        with hw_cols[0]:
                            cpu_cores = st.number_input(
                                "Max CPU Cores", 
                                min_value=1, 
                                max_value=128, 
                                value=int(v.get('max_cpu_cores') or 4),
                                key=f"cpu_{v['ip']}"
                            )
                        with hw_cols[1]:
                            ram_gb = st.number_input(
                                "Max RAM (GB)", 
                                min_value=0.5, 
                                max_value=1024.0, 
                                value=float(v.get('max_ram_gb') or 8.0),
                                step=0.5,
                                key=f"ram_{v['ip']}"
                            )
                        with hw_cols[2]:
                            disk_gb = st.number_input(
                                "Max Disk (GB)", 
                                min_value=1.0, 
                                max_value=10000.0, 
                                value=float(v.get('max_disk_gb') or 100.0),
                                step=1.0,
                                key=f"disk_{v['ip']}"
                            )
                    
                    with c3:
                        if st.button("💾 Update HW", key=f"save_hw_{v['ip']}", use_container_width=True):
                            db.update_vps_hardware(v['ip'], cpu_cores, ram_gb, disk_gb)
                            st.success("Updated!")
                            st.rerun()
                        
                        if st.button("🗑️ Remove", key=f"r_{v['ip']}", use_container_width=True): 
                            db.remove_vps(v['ip'])
                            st.success(f"Removed {v['name']}")
                            st.rerun()
        else:
            st.info("No VPS configured yet.")
    
    # ==================== TAB 4: HISTORY & EXPORT ====================
    with tab4:
        st.subheader("📜 Historical Data & Export")
        
        # Export controls
        col1, col2 = st.columns([3, 1])
        
        with col1:
            export_days = st.selectbox("Export Duration", options=[7, 30, 90], format_func=lambda x: f"Last {x} Days")
        
        with col2:
            if st.button("📥 Prepare System CSV", use_container_width=True):
                st_time = int(time.time()) - (export_days * 86400)
                hist = db.get_history(start_time=st_time, limit=10000)
                
                if hist:
                    df = pd.DataFrame(hist)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="💾 Download CSV",
                        data=csv,
                        file_name=f"pulse_export_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No data to export")
        
        # Display recent history
        st.subheader("Recent Activity")
        recent = db.get_history(limit=100)
        
        if recent:
            df = pd.DataFrame(recent)
            df['timestamp'] = df['timestamp'].apply(format_timestamp)
            
            st.dataframe(
                df[['timestamp', 'vps_name', 'vps_ip', 'status', 'cpu_percent', 'ram_percent', 'disk_percent', 'latency_ms']],
                use_container_width=True,
                height=400
            )
        else:
            st.info("No historical data yet.")
    
    # ==================== TAB 5: DEBUG/RAW METRICS ====================
    with tab_debug:
        st.subheader("🔍 Debug & Raw Metrics Viewer")
        st.caption("Test VPS connections and view raw metric values for troubleshooting")
        
        vps_list_debug = db.list_vps()
        if not vps_list_debug:
            st.warning("No VPS configured. Go to Nucleus Config to add VPS.")
        else:
            # VPS selector
            vps_debug_options = {f"{vps['name']} ({vps['ip']})": vps for vps in vps_list_debug}
            selected_debug_vps = st.selectbox("Select VPS to Test", options=list(vps_debug_options.keys()))
            
            if selected_debug_vps:
                vps = vps_debug_options[selected_debug_vps]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**VPS Configuration:**")
                    st.json({
                        "IP": vps['ip'],
                        "Name": vps['name'],
                        "Node Exporter Port": vps.get('port', 9100),
                        "cAdvisor Port": vps.get('cadvisor_port', 8080),
                        "Max CPU Cores": vps.get('max_cpu_cores', 4),
                        "Max RAM GB": vps.get('max_ram_gb', 8.0),
                        "Max Disk GB": vps.get('max_disk_gb', 100.0),
                        "Enabled": vps.get('enabled') == 1
                    })
                
                with col2:
                    st.write("**Latest Database Entry:**")
                    latest_db = db.get_latest_status(vps['ip'])
                    if latest_db:
                        st.json({
                            "Status": latest_db.get('status'),
                            "CPU %": latest_db.get('cpu_percent'),
                            "RAM %": latest_db.get('ram_percent'),
                            "Disk %": latest_db.get('disk_percent'),
                            "Latency ms": latest_db.get('latency_ms'),
                            "Timestamp": format_timestamp(latest_db['timestamp'])
                        })
                    else:
                        st.info("No data in database yet")
                
                st.divider()
                
                # Test live scrape
                if st.button("🔄 Test Live Scrape", use_container_width=True):
                    with st.spinner("Scraping metrics..."):
                        try:
                            metrics = scrape_vps(
                                host=vps['ip'],
                                node_port=vps.get('port', 9100),
                                cadvisor_port=vps.get('cadvisor_port', 8080),
                                include_docker=True
                            )
                            
                            # Auto-update hardware on manual scrape too
                            if metrics.get('hardware'):
                                hw = metrics['hardware']
                                if hw.get('cpu_cores') or hw.get('ram_gb') or hw.get('disk_gb'):
                                    db.update_vps_hardware(
                                        vps['ip'], 
                                        max_cpu_cores=hw.get('cpu_cores'),
                                        max_ram_gb=hw.get('ram_gb'),
                                        max_disk_gb=hw.get('disk_gb')
                                    )
                                    st.toast(f"Updated hardware info: {hw}")
                            
                            st.success("✅ Scrape successful!")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write("**System Metrics:**")
                                st.json({
                                    "Status": metrics.get('status'),
                                    "Latency (ms)": metrics.get('latency_ms'),
                                    "CPU %": metrics.get('cpu_percent'),
                                    "RAM %": metrics.get('ram_percent'),
                                    "Disk %": metrics.get('disk_percent')
                                })
                            
                            with col2:
                                st.write("**Docker Containers:**")
                                containers = metrics.get('docker_containers', [])
                                if containers:
                                    st.write(f"Found {len(containers)} containers")
                                    for c in containers[:10]:  # Show first 10
                                        with st.expander(f"🐳 {c['name']}"):
                                            st.write(f"**CPU:** {c.get('cpu_percent', 0):.2f}%")
                                            st.write(f"**Memory:** {c.get('memory_mb', 0):.2f} MB")
                                            st.write(f"**Status:** {c.get('status', 'UNKNOWN')}")
                                else:
                                    st.info("No Docker containers found")
                            
                            # Show full raw response
                            with st.expander("📋 Full Metrics Object (JSON)"):
                                st.json(metrics)
                        
                        except Exception as e:
                            st.error(f"❌ Scrape failed: {str(e)}")
                            st.exception(e)

    # Developer Signature - Bottom Center
    st.markdown("""
        <div class="footer">
            Desarrollado por Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
        </div>
    """, unsafe_allow_html=True)


def render_vps_card(vps: dict) -> str:
    """Render a VPS status card with metrics and emoji details."""
    latest = db.get_latest_status(vps['ip'])
    status = latest['status'] if latest else 'DOWN'
    latency = (latest.get('latency_ms') or 0.0) if latest else 0.0
    cpu = (latest.get('cpu_percent') or 0.0) if latest else 0.0
    ram = (latest.get('ram_percent') or 0.0) if latest else 0.0
    disk = (latest.get('disk_percent') or 0.0) if latest else 0.0
    
    # Get hardware limits
    max_cpu_cores = vps.get('max_cpu_cores') or 4
    max_ram_gb = vps.get('max_ram_gb') or 8.0
    max_disk_gb = vps.get('max_disk_gb') or 100.0
    
    # Detect overshoot (metrics > 100%)
    is_overshoot = (cpu > 100) or (ram > 100) or (disk > 100)
    
    # Detect gap (stale data)
    now = int(time.time())
    daemon = get_monitor_daemon()
    interval = daemon.get_status()['interval']
    is_stale = latest and (now - latest['timestamp']) > (interval + 10)
    
    # Determine card class
    if status == 'DOWN' or is_overshoot or is_stale:
        card_class = "status-card-down"
    else:
        card_class = "status-card-up"
    
    docker_containers = db.get_latest_docker_snapshot(vps['ip']) or []
    docker_html = f"<div style='margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); padding-top:5px;'><small>🐳 Docker: {len(docker_containers)} conts</small></div>" if docker_containers else ""
    
    # Add overshoot or stale warning badge
    warning_badge = ""
    if is_overshoot:
        warning_badge = '<span class="metric-badge badge-danger">⚠️ OVERSHOOT</span>'
    elif is_stale:
        warning_badge = '<span class="metric-badge badge-danger">⚠️ STALE DATA</span>'
    
    return f"""
    <div class="{card_class}">
        <h3 style="margin: 0;">{vps['name']}</h3>
        <p style="font-family: monospace; margin:0;">{vps['ip']} {get_status_badge(status)} {warning_badge}</p>
        <div style="margin-top:10px; font-size:14px;">
            ⚡ {latency:.1f}ms | 💻 {cpu:.1f}% | 🧠 {ram:.1f}% | 💾 {disk:.1f}%
        </div>
        {docker_html}
    </div>
    """


def render_security_card(vps: dict) -> str:
    """Render a security summarized card with badges and ports."""
    latest = db.get_latest_security_snapshot(vps['ip'])
    if not latest:
        return f'<div class="status-card-sec"><h3>{vps["name"]}</h3><p>Waiting for audit...</p></div>'
    
    fw_status = latest.get("firewall", "unknown")
    fw_badge = '<span class="metric-badge badge-success">FW: ON</span>' if fw_status == "active" else '<span class="metric-badge badge-danger">FW: OFF</span>'
    
    f2b_status = latest.get("fail2ban", "unknown")
    f2b_badge = '<span class="metric-badge badge-success">F2B</span>' if f2b_status == "running" else '<span class="metric-badge badge-danger">F2B</span>'
    
    selinux_status = latest.get("selinux", "unknown")
    selinux_badge = '<span class="metric-badge badge-success">SELinux</span>' if selinux_status == "enforcing" else '<span class="metric-badge badge-danger">SELinux</span>'
    
    # Detect security issues
    is_insecure = (fw_status != "active") or (f2b_status != "running") or (selinux_status != "enforcing")
    card_class = "status-card-down" if is_insecure else "status-card-sec"
    
    ports = latest.get("open_ports", [])
    ports_preview = ", ".join([str(p['port']) for p in ports[:4]])
    if len(ports) > 4: ports_preview += "..."
    
    # Active traffic summary
    active = latest.get("active_ports", [])
    total_rx = sum(p.get('rx_kbps', 0) for p in active)
    
    return f"""
    <div class="{card_class}">
        <h3 style="margin: 0; color: #00d4ff;">{vps['name']}</h3>
        <p style="margin: 5px 0;">{fw_badge} {f2b_badge} {selinux_badge}</p>
        <div class="port-metric">
            🔓 Open Ports: {ports_preview or 'None'}<br>
            🌐 Active Load: {total_rx:.1f} KB/s
        </div>
    </div>
    """

# ========== ENTRY POINT ==========

if __name__ == "__main__":
    main()
