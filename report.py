"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Scheduled Reporting Module.

ARCHITECTURAL DECISION:
- Uses `APScheduler` for weekly/monthly jobs independent of user interaction.
- Generates static PDF/PNG snapshots of performance to provide long-term trend analysis for stakeholders.
"""

import logging
import time
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import List, Dict, Any
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from apscheduler.schedulers.background import BackgroundScheduler

import db
import notification


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global scheduler instance
_scheduler: BackgroundScheduler = None


def init_scheduler():
    """
    Initialize and start the report scheduler.
    
    Configures weekly (Monday 8 AM) and monthly (1st day 8 AM) reports.
    """
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running")
        return
    
    _scheduler = BackgroundScheduler()
    
    # Weekly report: Every Monday at 8:00 AM
    _scheduler.add_job(
        weekly_report,
        trigger='cron',
        day_of_week='mon',
        hour=8,
        minute=0,
        id='weekly_report'
    )
    
    # Monthly report: 1st day of month at 8:00 AM
    _scheduler.add_job(
        monthly_report,
        trigger='cron',
        day=1,
        hour=8,
        minute=0,
        id='monthly_report'
    )
    
    _scheduler.start()
    logger.info("✓ Report scheduler initialized (weekly: Mon 08:00, monthly: 1st 08:00)")


def stop_scheduler():
    """Stop the report scheduler."""
    global _scheduler
    
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Report scheduler stopped")


def weekly_report():
    """Generate and send weekly performance report."""
    try:
        logger.info("Generating weekly report...")
        
        # Calculate date range (last 7 days)
        end_time = int(time.time())
        start_time = end_time - (7 * 24 * 3600)
        
        # Generate report
        csv_bytes, png_bytes = _generate_report(start_time, end_time, "Weekly")
        
        # Send email
        subject = f"📊 Weekly Infrastructure Report - {datetime.now().strftime('%Y-%m-%d')}"
        body_html = _create_report_html("Weekly", start_time, end_time)
        
        notification.send_report(subject, body_html, csv_bytes, png_bytes)
        
        logger.info("✓ Weekly report sent")
    
    except Exception as e:
        logger.error(f"Weekly report failed: {e}", exc_info=True)


def monthly_report():
    """Generate and send monthly performance report."""
    try:
        logger.info("Generating monthly report...")
        
        # Calculate date range (last 30 days)
        end_time = int(time.time())
        start_time = end_time - (30 * 24 * 3600)
        
        # Generate report
        csv_bytes, png_bytes = _generate_report(start_time, end_time, "Monthly")
        
        # Send email
        subject = f"📊 Monthly Infrastructure Report - {datetime.now().strftime('%Y-%m')}"
        body_html = _create_report_html("Monthly", start_time, end_time)
        
        notification.send_report(subject, body_html, csv_bytes, png_bytes)
        
        logger.info("✓ Monthly report sent")
    
    except Exception as e:
        logger.error(f"Monthly report failed: {e}", exc_info=True)


def _generate_report(start_time: int, end_time: int, period: str) -> tuple:
    """
    Generate CSV and PNG for a reporting period.
    
    Args:
        start_time: Start timestamp
        end_time: End timestamp
        period: "Weekly" or "Monthly"
        
    Returns:
        Tuple of (csv_bytes, png_bytes)
    """
    # Get all VPS
    vps_list = db.list_vps()
    
    if not vps_list:
        logger.warning("No VPS configured for report")
        return None, None
    
    # Collect metrics for each VPS
    all_data = []
    
    for vps in vps_list:
        history = db.get_history(
            vps_ip=vps['ip'],
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        
        if history:
            for record in history:
                all_data.append({
                    'vps_name': record['vps_name'],
                    'vps_ip': record['vps_ip'],
                    'timestamp': datetime.fromtimestamp(record['timestamp']),
                    'status': record['status'],
                    'latency_ms': record['latency_ms'],
                    'cpu_percent': record['cpu_percent'],
                    'ram_percent': record['ram_percent'],
                    'disk_percent': record['disk_percent']
                })
    
    if not all_data:
        logger.warning("No data available for report")
        return None, None
    
    # Create DataFrame
    df = pd.DataFrame(all_data)
    
    # Generate CSV
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode('utf-8')
    
    # Generate trend graph
    png_bytes = _create_trend_graph(df, period)
    
    return csv_bytes, png_bytes


def _create_trend_graph(df: pd.DataFrame, period: str) -> bytes:
    """
    Create a trend graph showing average metrics over time.
    
    Args:
        df: DataFrame with metrics
        period: Report period label
        
    Returns:
        PNG as bytes
    """
    try:
        # Group by VPS and calculate daily averages
        df['date'] = df['timestamp'].dt.date
        daily_avg = df.groupby(['vps_name', 'date']).agg({
            'cpu_percent': 'mean',
            'ram_percent': 'mean',
            'disk_percent': 'mean'
        }).reset_index()
        
        # Create figure
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), facecolor='#1a1a1a')
        fig.suptitle(f'{period} Infrastructure Trends', fontsize=16, color='white', fontweight='bold')
        
        # Plot each VPS
        for vps_name in daily_avg['vps_name'].unique():
            vps_data = daily_avg[daily_avg['vps_name'] == vps_name]
            
            ax1.plot(vps_data['date'], vps_data['cpu_percent'], marker='o', label=vps_name, linewidth=2)
            ax2.plot(vps_data['date'], vps_data['ram_percent'], marker='o', label=vps_name, linewidth=2)
            ax3.plot(vps_data['date'], vps_data['disk_percent'], marker='o', label=vps_name, linewidth=2)
        
        # Style axes
        axes = [ax1, ax2, ax3]
        titles = ['Average CPU Usage (%)', 'Average RAM Usage (%)', 'Average Disk Usage (%)']
        
        for ax, title in zip(axes, titles):
            ax.set_facecolor('#0e1117')
            ax.set_ylabel(title, color='white', fontsize=11, fontweight='bold')
            ax.tick_params(colors='white', labelsize=9)
            ax.grid(True, alpha=0.2, color='gray', linestyle='--')
            ax.legend(facecolor='#1a1a1a', edgecolor='white', labelcolor='white')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_color('white')
            ax.spines['left'].set_color('white')
            ax.set_ylim(0, 100)
        
        ax3.set_xlabel('Date', color='white', fontsize=11, fontweight='bold')
        
        plt.tight_layout()
        
        # Save to bytes
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a')
        plt.close(fig)
        
        buf.seek(0)
        return buf.read()
    
    except Exception as e:
        logger.error(f"Trend graph error: {e}", exc_info=True)
        return b''


def _create_report_html(period: str, start_time: int, end_time: int) -> str:
    """Create HTML email body for report."""
    start_date = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
    end_date = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d')
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background-color: #0e1117;
                color: #ffffff;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                border: 2px solid #00ff00;
                border-radius: 12px;
                padding: 30px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            h1 {{
                color: #00ff00;
                margin: 0;
                font-size: 24px;
            }}
            .period {{
                color: #888;
                margin-top: 10px;
            }}
            .content {{
                background-color: rgba(255, 255, 255, 0.05);
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                text-align: center;
                color: #888;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 {period} Infrastructure Report</h1>
                <div class="period">{start_date} to {end_date}</div>
            </div>
            
            <div class="content">
                <p>Your {period.lower()} infrastructure performance report is ready.</p>
                <p>Attached files:</p>
                <ul>
                    <li><strong>report.csv</strong> - Detailed metrics export</li>
                    <li><strong>metrics_graph.png</strong> - Trend visualization</li>
                </ul>
            </div>
            
            <div class="footer">
                Aigents Pulse v3.0 (Spectre) - Infrastructure Observability Platform<br>
                Automated {period.lower()} report from your monitoring system
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


# ========== MANUAL REPORT GENERATION ==========

def generate_custom_report(days: int = 7) -> tuple:
    """
    Generate a custom report for the last N days.
    
    Args:
        days: Number of days to include
        
    Returns:
        Tuple of (csv_bytes, png_bytes)
    """
    end_time = int(time.time())
    start_time = end_time - (days * 24 * 3600)
    
    return _generate_report(start_time, end_time, f"{days}-Day")
