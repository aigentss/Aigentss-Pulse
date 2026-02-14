"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Simple heartbeat signal generator for external health checks.
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
