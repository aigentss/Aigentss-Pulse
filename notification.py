"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

SMTP Notification Service.

ARCHITECTURAL DECISION:
- Uses Fernet symmetric encryption (AES-256) for storing SMTP credentials in `.env` vs plain text.
"""

import os
import smtplib
import logging
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email. mime.base import MIMEBase
from email import encoders
from typing import Optional
import ssl
from cryptography.fernet import Fernet


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== ENCRYPTION/DECRYPTION ==========

def decrypt_credential(encrypted: str) -> str:
    """
    Decrypt a Fernet-encrypted credential.
    
    Args:
        encrypted: Base64-encoded encrypted string
        
    Returns:
        Decrypted string
    """
    key = os.getenv("FERNET_KEY")
    if not key:
        raise ValueError("FERNET_KEY not found in environment")
    
    cipher = Fernet(key.encode())
    return cipher.decrypt(encrypted.encode()).decode()


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential using Fernet.
    
    Args:
        plaintext: Plain text to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    key = os.getenv("FERNET_KEY")
    if not key:
        raise ValueError("FERNET_KEY not found in environment")
    
    cipher = Fernet(key.encode())
    return cipher.encrypt(plaintext.encode()).decode()


# ========== EMAIL TEMPLATES ==========

ALERT_HTML_TEMPLATE = """
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
            border: 2px solid #ff0000;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .alert-icon {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
        h1 {{
            color: #ff0000;
            margin: 0;
            font-size: 24px;
        }}
        .info {{
            background-color: rgba(255, 255, 255, 0.05);
            border-left: 4px solid #00ff00;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
        }}
        .label {{
            color: #888;
            font-weight: 600;
        }}
        .value {{
            color: #fff;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
            color: #888;
            font-size: 12px;
        }}
        .graph-note {{
            text-align: center;
            color: #00d4ff;
            margin: 20px 0;
            font-size: 14px;
        }}
        .sec-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            overflow: hidden;
        }}
        .sec-table td, .sec-table th {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .badge-green {{ background: #00ff41; color: #000; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
        .badge-red {{ background: #ff0000; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="alert-icon">{icon}</div>
            <h1>{title}</h1>
        </div>
        
        <div class="info">
            <div class="info-row">
                <span class="label">VPS Name:</span>
                <span class="value">{vps_name}</span>
            </div>
            <div class="info-row">
                <span class="label">IP Address:</span>
                <span class="value">{vps_ip}</span>
            </div>
            <div class="info-row">
                <span class="label">Criticality:</span>
                <span class="value" style="color: {color};">{level}</span>
            </div>
            <div class="info-row">
                <span class="label">Timestamp:</span>
                <span class="value">{timestamp}</span>
            </div>
        </div>
        
        {extra_html}
        
        <div class="graph-note">
            📊 Result graph attached below
        </div>
        
        <div class="footer">
            Aigents Pulse v3.1 (Spectre+) - Infrastructure Observability Platform<br>
            Automated alert from your monitoring system
        </div>
    </div>
</body>
</html>
"""


# ========== SMTP FUNCTIONS ==========

def send_alert(
    vps_ip: str, 
    vps_name: str, 
    graph_png: bytes, 
    system_history: Optional[list] = None,
    docker_history: Optional[list] = None,
    security_state: Optional[dict] = None,
    retries: int = 3
) -> bool:
    """
    Send an enriched alert email (System, Docker, or Security).
    """
    for attempt in range(retries):
        try:
            # ... (SMTP setup as before)
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user_enc = os.getenv("SMTP_USER_ENC")
            smtp_pass_enc = os.getenv("SMTP_PASS_ENC")
            alert_email = os.getenv("ALERT_EMAIL")
            
            if not all([smtp_user_enc, smtp_pass_enc, alert_email]): return False
            smtp_user = decrypt_credential(smtp_user_enc); smtp_pass = decrypt_credential(smtp_pass_enc)
            
            # 1. Determine Alert Type & Context
            icon = "🚨"; title = "VPS DOWN Alert"; color = "#ff0000"; level = "CRITICAL"
            extra_html = ""
            
            if security_state:
                icon = "🔒"; title = "SECURITY Audit Alert"; color = "#ff9500"; level = "WARNING"
                # Build security table
                rows = []
                checks = {
                    "firewall": ("Firewall", "active"),
                    "fail2ban": ("Fail2Ban", "running"),
                    "auditd": ("Auditd", "running"),
                    "selinux": ("SELinux", "enforcing")
                }
                for key, (label, target) in checks.items():
                    val = security_state.get(key, "unknown")
                    status_cls = "badge-green" if val == target else "badge-red"
                    rows.append(f"<tr><td>{label}</td><td><span class='{status_cls}'>{val.upper()}</span></td></tr>")
                
                extra_html = f"<table class='sec-table'>{''.join(rows)}</table>"

            # 2. Build Message
            msg = MIMEMultipart('related')
            msg['From'] = smtp_user; msg['To'] = alert_email; msg['Subject'] = f'{icon} {title}: {vps_name}'
            
            from datetime import datetime
            html_content = ALERT_HTML_TEMPLATE.format(
                icon=icon, title=title, color=color, level=level,
                vps_name=vps_name, vps_ip=vps_ip,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
                extra_html=extra_html
            )
            msg.attach(MIMEText(html_content, 'html'))
            
            # Attach graph
            image = MIMEImage(graph_png, name='alert_intelligence.png')
            msg.attach(image)
            
            # ... Send
            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return True
            
        except Exception as e:
            if attempt < retries - 1: time.sleep(2**attempt)
            else: logger.error(f"Alert failed: {e}"); return False
    return False


def send_report(
    subject: str,
    body_html: str,
    csv_attachment: Optional[bytes] = None,
    png_attachment: Optional[bytes] = None,
    retries: int = 3
) -> bool:
    """
    Send a report email with optional CSV and PNG attachments.
    
    Args:
        subject: Email subject
        body_html: HTML email body
        csv_attachment: CSV file as bytes (optional)
        png_attachment: PNG graph as bytes (optional)
        retries: Number of retry attempts
        
    Returns:
        True if sent successfully, False otherwise
    """
    for attempt in range(retries):
        try:
            # Get SMTP configuration
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user_enc = os.getenv("SMTP_USER_ENC")
            smtp_pass_enc = os.getenv("SMTP_PASS_ENC")
            alert_email = os.getenv("ALERT_EMAIL")
            
            if not all([smtp_user_enc, smtp_pass_enc, alert_email]):
                logger.error("SMTP credentials not configured")
                return False
            
            # Decrypt credentials
            smtp_user = decrypt_credential(smtp_user_enc)
            smtp_pass = decrypt_credential(smtp_pass_enc)
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = alert_email
            msg['Subject'] = subject
            
            # Attach HTML body
            msg.attach(MIMEText(body_html, 'html'))
            
            # Attach CSV if provided
            if csv_attachment:
                csv_part = MIMEBase('application', 'octet-stream')
                csv_part.set_payload(csv_attachment)
                encoders.encode_base64(csv_part)
                csv_part.add_header('Content-Disposition', 'attachment; filename="report.csv"')
                msg.attach(csv_part)
            
            # Attach PNG if provided
            if png_attachment:
                image = MIMEImage(png_attachment, name='metrics_graph.png')
                msg.attach(image)
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            logger.info(f"✓ Report sent: {subject}")
            return True
        
        except Exception as e:
            if attempt < retries - 1:
                delay = 2 ** attempt
                logger.warning(f"Report send failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"Failed to send report after {retries} attempts: {e}")
                return False
    
    return False
