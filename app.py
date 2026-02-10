"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Elite UI/UX for Infrastructure Observability. 
Provides dual themes, real-time metrics, and Docker container sub-dashboards.
"""

import streamlit as st
import os
import time
from datetime import datetime, timedelta
import pandas as pd
import logging
import json

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
    tab_sec, tab1, tab2, tab3, tab4 = st.tabs([
        "Security",
        "Status Live",
        "Analytics",
        "Nucleus Config",
        "History & Export"
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
                                "Container": c['name'],
                                "Status": c.get('status', 'RUNNING'),
                                "CPU %": c.get('cpu_percent', 0.0),
                                "Memory GB": round((c.get('memory_mb', 0.0) / 1024.0), 3)
                            })
                    df_docker = pd.DataFrame(hist_data)

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
                                        st.line_chart(c_hist.set_index('Time')['CPU %'], height=60, use_container_width=True)

                    st.divider()
                    
                    # Global VPS Resource Summary
                    st.subheader("Global Docker vs System Summary")
                    view_vps_ip = ip # Use the 'ip' variable from the outer scope
                    vps_latest = db.get_latest_status(view_vps_ip)
                    if vps_latest and not df_docker.empty:
                        last_ts = df_docker['Time'].iloc[0]
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
            selected_vps = st.multiselect("Select VPS", options=list(vps_options.keys()), default=list(vps_options.keys())[:3] if vps_options else [])
        with col2:
            metric_type = st.selectbox("Metric Type", options=["CPU %", "RAM %", "Disk %", "Latency (ms)"])
        with col3:
            time_range = st.selectbox("Time Range", options=["Last 6 Hours", "Last 24 Hours", "Last 7 Days", "Last 30 Days"])
        
        hours_map = {"Last 6 Hours": 6, "Last 24 Hours": 24, "Last 7 Days": 24 * 7, "Last 30 Days": 24 * 30}
        start_time = int(time.time()) - (hours_map[time_range] * 3600)
        
        if selected_vps:
            chart_data = []
            for vps_name in selected_vps:
                history = db.get_history(vps_ip=vps_options[vps_name], start_time=start_time, limit=5000)
                for record in history:
                    val = record['cpu_percent'] if metric_type == "CPU %" else record['ram_percent'] if metric_type == "RAM %" else record['disk_percent'] if metric_type == "Disk %" else record['latency_ms']
                    if val is not None: chart_data.append({'Time': datetime.fromtimestamp(record['timestamp']), 'VPS': vps_name, metric_type: val})
            
            if chart_data:
                df = pd.DataFrame(chart_data)
                st.line_chart(df.pivot(index='Time', columns='VPS', values=metric_type), height=400)
                
                # Summary statistics
                st.subheader("Summary Statistics")
                summary_cols = st.columns(len(selected_vps))
                
                for i, vps_name in enumerate(selected_vps):
                    with summary_cols[i]:
                        vps_data = df[df['VPS'] == vps_name][metric_type]
                        if not vps_data.empty:
                            st.metric(
                                label=vps_name,
                                value=f"{vps_data.mean():.2f}",
                                delta=f"Max: {vps_data.max():.2f}"
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
            for v in vps_inv:
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{v['name']}** ({v['ip']})")
                if c2.checkbox("Active", v['enabled'] == 1, key=f"v_{v['ip']}"): 
                    if not (v['enabled'] == 1): db.update_vps(v['ip'], enabled=True)
                else: 
                    if (v['enabled'] == 1): db.update_vps(v['ip'], enabled=False)
                if c3.button("🗑️", key=f"r_{v['ip']}"): 
                    db.remove_vps(v['ip']); st.success(f"Removed {v['name']}"); st.rerun()
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
    
    docker_containers = db.get_latest_docker_snapshot(vps['ip']) or []
    card_class = "status-card-up" if status == "UP" else "status-card-down"
    
    docker_html = f"<div style='margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); padding-top:5px;'><small>🐳 Docker: {len(docker_containers)} conts</small></div>" if docker_containers else ""
    
    return f"""
    <div class="{card_class}">
        <h3 style="margin: 0;">{vps['name']}</h3>
        <p style="font-family: monospace; margin:0;">{vps['ip']} {get_status_badge(status)}</p>
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
    
    ports = latest.get("open_ports", [])
    ports_preview = ", ".join([str(p['port']) for p in ports[:4]])
    if len(ports) > 4: ports_preview += "..."
    
    # Active traffic summary
    active = latest.get("active_ports", [])
    total_rx = sum(p.get('rx_kbps', 0) for p in active)
    
    return f"""
    <div class="status-card-sec">
        <h3 style="margin: 0; color: #00d4ff;">{vps['name']}</h3>
        <p style="margin: 5px 0;">{fw_badge} {f2b_badge}</p>
        <div class="port-metric">
            🔓 Open Ports: {ports_preview or 'None'}<br>
            🌐 Active Load: {total_rx:.1f} KB/s
        </div>
    </div>
    """

# ========== ENTRY POINT ==========

if __name__ == "__main__":
    main()
