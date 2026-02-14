#!/usr/bin/env python3
"""
Debug script to test cAdvisor metric parsing locally
"""
import sys
sys.path.insert(0, '/Users/Rattio/rfid_rgb_app/aigents/2026/DevOps/Aigentss-Pulse')

from prometheus_metrics import scrape_vps
import json

print("Testing Hostinger metrics...")
result = scrape_vps(
    host="82.25.84.232",
    node_port=9100,
    cadvisor_port=8080,
    include_docker=True
)

containers = result.get('docker_containers', [])

print(f"\nFound {len(containers)} containers")
print("\nFirst 5 containers:")
for c in containers[:5]:
    print(f"  {c['name']}: CPU={c['cpu_percent']}%, MEM={c['memory_mb']} MB")

# Check if all have same memory
unique_mems = set(c['memory_mb'] for c in containers)
print(f"\nUnique memory values: {len(unique_mems)}")
if len(unique_mems) == 1:
    print(f"⚠️  ALL containers have identical memory: {list(unique_mems)[0]} MB")
    print(f"   This is {list(unique_mems)[0] / 1024:.2f} GB")
    print(f"   In bytes: {list(unique_mems)[0] * 1024 * 1024:.0f}")
else:
    print(f"✓ Memory values vary correctly")
    for mem in sorted(unique_mems)[:10]:
        print(f"  {mem} MB = {mem/1024:.3f} GB")
