"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

Heartbeat Generator.

ARCHITECTURAL DECISION:
- Minimalist script to signal 'I am alive' to external watchdogs.
"""

import psutil

def get_vital_signs():
    """
    Collects internal health metrics: CPU, RAM, Disk usage.
    Returns a dictionary with percentage values.
    """
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        return {
            'cpu': cpu,
            'ram': ram,
            'disk': disk
        }
    except Exception as e:
        return {
            'cpu': 0,
            'ram': 0,
            'disk': 0
        }
