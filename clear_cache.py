"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

Maintenance Utility.

ARCHITECTURAL DECISION:
- Clears Streamlit internal cache and compiled byte-code.
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
