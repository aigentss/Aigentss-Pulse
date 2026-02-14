"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Alerting Engine.

ARCHITECTURAL DECISION:
- State-based triggering: Checks for transitions (UP -> DOWN) rather than continuous failed states to reduce alert fatigue.
- Embeds visual evidence (PNG graphs) directly in emails using Matplotlib backend to provide immediate context without logging in.
"""

import hashlib
import json
import logging
import time
from io import BytesIO
from typing import Optional, Tuple, List, Dict, Any
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

import db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_and_alert(vps_ip: str, vps_name: str, current_status: str) -> None:
    """
    Check if an alert should be triggered and send it.
    
    Alerts are sent when a VPS transitions from UP to DOWN.
    Includes 24h of historical data for both system and Docker.
    """
    try:
        # Get previous alert state
        alert_state = db.get_alert_state(vps_ip)
        
        # Determine if we should alert
        should_alert = False
        
        if alert_state is None:
            # First time seeing this VPS - initialize state
            db.update_alert_state(vps_ip, current_status, None)
            last_status = None
        else:
            last_status = alert_state['last_status']
        
        # Detect UP→DOWN transition
        if last_status == 'UP' and current_status == 'DOWN':
            should_alert = True
        
        # Update state if status changed
        if current_status != last_status:
            timestamp = int(time.time()) if should_alert else None
            db.update_alert_state(vps_ip, current_status, timestamp)
        
        # Send alert if needed
        if should_alert:
            logger.warning(f"🚨 ALERT: {vps_name} ({vps_ip}) is DOWN!")
            
            # 1. Generate 24h system graph
            graph_bytes = generate_24h_graph(vps_ip, vps_name)
            
            # 2. Gather 24h Docker history
            docker_history = db.get_docker_history(vps_ip, limit=100)
            
            # 3. Gather 24h System history (raw data for CSV)
            system_history = db.get_last_24h(vps_ip)
            
            # Send notification with full intelligence
            try:
                import notification
                notification.send_alert(
                    vps_ip=vps_ip, 
                    vps_name=vps_name, 
                    graph_png=graph_bytes,
                    system_history=system_history,
                    docker_history=docker_history
                )
            except Exception as e:
                logger.error(f"Failed to send alert notification: {e}")
    
    except Exception as e:
        logger.error(f"Alert check error for {vps_name}: {e}", exc_info=True)


def check_and_alert_security(vps_ip: str, vps_name: str, security_state: Dict[str, Any]) -> None:
    """
    Check for critical changes in VPS security configuration.
    Triggers an alert if a security hash mismatch is detected.
    """
    try:
        alert_state = db.get_alert_state(vps_ip)
        current_hash = _hash_security(security_state)
        
        should_alert = False
        if alert_state and alert_state.get('last_security_hash'):
            if alert_state['last_security_hash'] != current_hash:
                # Security change detected - alert if critical
                # Simple check: if firewall or hardening changed
                should_alert = True
        
        # Update hash in DB
        db.update_alert_state(vps_ip, alert_state['last_status'] if alert_state else 'UP', security_hash=current_hash)
        
        if should_alert:
            logger.warning(f"🔒 SECURITY CHANGE: {vps_name} ({vps_ip}) state modified!")
            
            # Generate historical port traffic graph
            history = db.get_security_history(vps_ip, limit=30)
            graph_png = generate_port_graph(vps_name, history)
            
            # Send notification
            try:
                import notification
                notification.send_alert(
                    vps_ip=vps_ip,
                    vps_name=vps_name,
                    graph_png=graph_png,
                    security_state=security_state
                )
            except Exception as e:
                logger.error(f"Failed to send security alert: {e}")
                
    except Exception as e:
        logger.error(f"Security alert check failed for {vps_name}: {e}")

def _hash_security(state: Dict[str, Any]) -> str:
    """Generate a deterministic SHA256 hash of the security JSON."""
    canonical = json.dumps(state, sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()


def generate_24h_graph(vps_ip: str, vps_name: str) -> bytes:
    """
    Generate a 24-hour metrics graph as PNG bytes.
    
    Creates a 3-panel graph showing CPU, RAM, and Disk usage
    over the last 24 hours.
    
    Args:
        vps_ip: IP address of the VPS
        vps_name: Friendly name for the title
        
    Returns:
        PNG image as bytes
    """
    try:
        # Get 24h history
        history = db.get_last_24h(vps_ip)
        
        if not history:
            # No data - create placeholder
            return _create_empty_graph(vps_name)
        
        # Extract data
        timestamps = [datetime.fromtimestamp(row['timestamp']) for row in history]
        cpu_data = [row['cpu_percent'] if row['cpu_percent'] is not None else 0 for row in history]
        ram_data = [row['ram_percent'] if row['ram_percent'] is not None else 0 for row in history]
        disk_data = [row['disk_percent'] if row['disk_percent'] is not None else 0 for row in history]
        
        # Create figure with 3 subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8), facecolor='#1a1a1a')
        fig.suptitle(f'{vps_name} - Last 24 Hours', fontsize=16, color='white', fontweight='bold')
        
        # Style configuration
        axes = [ax1, ax2, ax3]
        data_sets = [
            (cpu_data, 'CPU Usage (%)', '#00ff41'),
            (ram_data, 'RAM Usage (%)', '#00d4ff'),
            (disk_data, 'Disk Usage (%)', '#ff9500')
        ]
        
        for ax, (data, label, color) in zip(axes, data_sets):
            ax.set_facecolor('#0e1117')
            ax.plot(timestamps, data, color=color, linewidth=2, marker='o', markersize=3)
            ax.fill_between(timestamps, data, alpha=0.3, color=color)
            ax.set_ylabel(label, color='white', fontsize=11, fontweight='bold')
            ax.tick_params(colors='white', labelsize=9)
            ax.grid(True, alpha=0.2, color='gray', linestyle='--')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_color('white')
            ax.spines['left'].set_color('white')
            
            # Add percentage labels
            ax.set_ylim(0, 100)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{int(y)}%'))
        
        # Format x-axis for bottom plot only
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax3.xaxis.set_major_locator(mdates.HourLocator(interval=4))
        plt.setp(ax1.get_xticklabels(), visible=False)
        plt.setp(ax2.get_xticklabels(), visible=False)
        ax3.set_xlabel('Time', color='white', fontsize=11, fontweight='bold')
        
        # Tight layout
        plt.tight_layout()
        
        # Save to bytes
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a', edgecolor='none')
        plt.close(fig)
        
        buf.seek(0)
        return buf.read()
    
    except Exception as e:
        logger.error(f"Graph generation error: {e}", exc_info=True)
        return _create_empty_graph(vps_name)


def _create_empty_graph(vps_name: str) -> bytes:
    """Create a placeholder graph when no data is available."""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#1a1a1a')
    ax.set_facecolor('#0e1117')
    ax.text(0.5, 0.5, f'No historical data for {vps_name}',
            horizontalalignment='center', verticalalignment='center',
            fontsize=16, color='white', transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a')
    plt.close(fig)
    
    buf.seek(0)
    return buf.read()


def generate_port_graph(vps_name: str, history: List[Dict[str, Any]]) -> bytes:
    """
    Generate a graph showing network throughput evolution for active ports.
    """
    try:
        import pandas as pd
        rows = []
        for snap in history:
            ts = datetime.fromtimestamp(snap["timestamp"])
            sec = json.loads(snap["security_json"])
            for p in sec.get("active_ports", []):
                rows.append({
                    "time": ts,
                    "port": f"{p['port']}/{p['protocol']}",
                    "rx": p["rx_kbps"],
                    "tx": p["tx_kbps"]
                })
        
        if not rows:
            return _create_empty_graph(vps_name)

        df = pd.DataFrame(rows)
        # Limit to top 5 ports by traffic to avoid clutter
        top_ports = df.groupby('port')[['rx', 'tx']].mean().sum(axis=1).sort_values(ascending=False).head(5).index
        df = df[df['port'].isin(top_ports)]

        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1a1a1a')
        ax.set_facecolor('#0e1117')
        
        for port, grp in df.groupby("port"):
            ax.plot(grp["time"], grp["rx"], label=f"{port} Rx", linewidth=2)
            ax.plot(grp["time"], grp["tx"], linestyle='--', label=f"{port} Tx", alpha=0.7)

        ax.set_title(f"Network Audit: {vps_name}", color='white', fontweight='bold', fontsize=14)
        ax.set_xlabel("Time", color='white')
        ax.set_ylabel("Throughput (KB/s)", color='white')
        ax.legend(facecolor='#1a1a1a', edgecolor='white', labelcolor='white', loc='upper left')
        ax.grid(True, alpha=0.1, color='gray')
        ax.tick_params(colors='white')
        
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a')
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"Port graph error: {e}")
        return _create_empty_graph(vps_name)
