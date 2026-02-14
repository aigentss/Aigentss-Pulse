"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Utility to clear Streamlit cache and pycache files.
"""

#!/usr/bin/env python3
"""
Clear Docker CPU cache to force recalculation of container metrics.
This resolves issues with stale/absurd cached values.
"""

import sys
sys.path.insert(0, '/Users/Rattio/rfid_rgb_app/aigents/2026/DevOps/Aigentss-Pulse')

import prometheus_metrics

print("Clearing Docker CPU cache...")
prometheus_metrics._DOCKER_CPU_CACHE.clear()
print(f"Cache cleared. Current cache state: {prometheus_metrics._DOCKER_CPU_CACHE}")
print("Done! Container CPU metrics will be recalculated on next scrape.")
