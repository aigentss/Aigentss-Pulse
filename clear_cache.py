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
