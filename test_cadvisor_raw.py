"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

Module: test_cadvisor_raw.py
Auto-generated description.
"""

#!/usr/bin/env python3
"""
Test script to download and inspect raw cAdvisor metrics from a VPS.
This helps identify the actual metric format we're receiving.
"""
import httpx
import sys

VPS_IP = "82.25.84.232"  # Hostinger
CADVISOR_PORT = 8080

print(f"Fetching cAdvisor metrics from {VPS_IP}:{CADVISOR_PORT}...")

try:
    response = httpx.get(f"http://{VPS_IP}:{CADVISOR_PORT}/metrics", timeout=10)
    metrics_text = response.text
    
    print(f"\nTotal response size: {len(metrics_text)} bytes\n")
    
    # Find all container_memory_working_set_bytes lines
    print("=" * 80)
    print("MEMORY METRICS (container_memory_working_set_bytes):")
    print("=" * 80)
    for line in metrics_text.split('\n'):
        if 'container_memory_working_set_bytes{' in line and 'name=' in line:
            print(line[:200])  # First 200 chars
    
    print("\n" + "=" * 80)
    print("CPU METRICS (container_cpu_usage_seconds_total):")
    print("=" * 80)
    count = 0
    for line in metrics_text.split('\n'):
        if 'container_cpu_usage_seconds_total{' in line and 'name="cadvisor"' in line:
            print(line[:250])
            count += 1
            if count >= 10:  # Show first 10 lines for cadvisor
                break
                
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
