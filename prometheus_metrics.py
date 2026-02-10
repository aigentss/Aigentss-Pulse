"""
Prometheus Node Exporter Metrics Fetcher
Fetches CPU, RAM, and Disk usage from prometheus-node-exporter endpoints.
Also fetches Docker container metrics if available.
"""

import requests
import re
import logging
from typing import Dict, Any, List

def get_node_metrics(ip_address: str, port: int = 9100, timeout: int = 2) -> Dict[str, float]:
    """
    Fetches system metrics from a Prometheus Node Exporter endpoint.
    Retrieves instantaneous CPU usage requires rate calculation, but for single-call statelessness,
    we currently approximate or would need state. 
    Ideally, Prometheus server does this. Here we try to get what we can.
    
    Args:
        ip_address: Target IP address
        port: Node Exporter port (default 9100)
        timeout: Request timeout in seconds
    
    Returns:
        dict with keys: cpu, ram, disk (percentage values)
    """
    metrics = {'cpu': 0.0, 'ram': 0.0, 'disk': 0.0}
    
    try:
        url = f"http://{ip_address}:{port}/metrics"
        response = requests.get(url, timeout=timeout)
        
        if response.status_code != 200:
            logging.warning(f"Node Exporter {ip_address}: HTTP {response.status_code}")
            return metrics
        
        text = response.text
        
        # --- RAM Usage ---
        # node_memory_MemTotal_bytes, node_memory_MemAvailable_bytes
        mem_total_match = re.search(r'node_memory_MemTotal_bytes\s+([\d.e+]+)', text)
        mem_avail_match = re.search(r'node_memory_MemAvailable_bytes\s+([\d.e+]+)', text)
        
        if mem_total_match and mem_avail_match:
            total = float(mem_total_match.group(1))
            available = float(mem_avail_match.group(1))
            if total > 0:
                used_pct = ((total - available) / total) * 100
                metrics['ram'] = round(used_pct, 1)
        
        # --- Disk Usage (root filesystem) ---
        # node_filesystem_size_bytes{...mountpoint="/",...}
        disk_size_match = re.search(r'node_filesystem_size_bytes\{[^}]*mountpoint="/",[^}]*\}\s+([\d.e+]+)', text)
        disk_avail_match = re.search(r'node_filesystem_avail_bytes\{[^}]*mountpoint="/",[^}]*\}\s+([\d.e+]+)', text)
        
        # Fallback: find any ext4/xfs if root not explicitly found like that
        if not disk_size_match:
             disk_size_match = re.search(r'node_filesystem_size_bytes\{[^}]*fstype="(?:ext4|xfs|btrfs)"[^}]*\}\s+([\d.e+]+)', text)
             disk_avail_match = re.search(r'node_filesystem_avail_bytes\{[^}]*fstype="(?:ext4|xfs|btrfs)"[^}]*\}\s+([\d.e+]+)', text)

        if disk_size_match and disk_avail_match:
            size = float(disk_size_match.group(1))
            avail = float(disk_avail_match.group(1))
            if size > 0:
                used_pct = ((size - avail) / size) * 100
                metrics['disk'] = round(used_pct, 1)
                
        # --- CPU Usage ---
        # Note: Without history, we can only calculate average since boot or 
        # use a specialized exporter field if available. 
        # node_cpu_seconds_total is a counter.
        # We will return a placeholder or average since boot if that's all we have.
        # For a better stateless approximation, we might look for 'node_load1'
        load1_match = re.search(r'node_load1\s+([\d.]+)', text)
        cpu_count_match = re.findall(r'node_cpu_seconds_total\{.*mode="idle"\}', text)
        
        if load1_match:
             # Very rough approximation: load1 / distinct_cores * 100
             # But we assume the user accepts load as proxy or we implement stateful diff in monitor.py
             # For now, let's stick to the previous implementation "100 - idle_pct (avg since boot)"
             # as it was in the original file, to avoid breaking behavior without state.
             pass

        cpu_idle_matches = re.findall(r'node_cpu_seconds_total\{[^}]*mode="idle"[^}]*\}\s+([\d.]+)', text)
        cpu_total_matches = re.findall(r'node_cpu_seconds_total\{[^}]*\}\s+([\d.]+)', text)
        
        if cpu_idle_matches and cpu_total_matches:
            idle_seconds = sum(float(m) for m in cpu_idle_matches)
            total_seconds = sum(float(m) for m in cpu_total_matches)
            if total_seconds > 0:
                idle_pct = (idle_seconds / total_seconds) * 100
                metrics['cpu'] = round(100 - idle_pct, 1)

        return metrics
        
    except requests.exceptions.Timeout:
        logging.debug(f"Node Exporter {ip_address}: Timeout")
        return metrics
    except requests.exceptions.ConnectionError:
        logging.debug(f"Node Exporter {ip_address}: Connection refused")
        return metrics
    except Exception as e:
        logging.error(f"Node Exporter {ip_address}: {e}")
        return metrics

def get_docker_metrics(ip_address: str, port: int = 9100, timeout: int = 2) -> List[Dict[str, Any]]:
    """
    Fetches container metrics if available exposed via the same endpoint.
    Looks for container_memory_usage_bytes and container_cpu_usage_seconds_total.
    
    Returns:
        List of dicts: [{'name': 'container_name', 'memory_bytes': 123, 'cpu_seconds': 456, 'type': 'db'|'app'}]
    """
    containers = {}
    
    try:
        url = f"http://{ip_address}:{port}/metrics"
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            return []
        
        text = response.text
        
        # Regex to find container metrics with name label
        # container_memory_usage_bytes{...name="foo"...} 12345
        mem_pattern = r'container_memory_usage_bytes\{[^}]*name="([^"]+)"[^}]*\}\s+([\d.e+]+)'
        cpu_pattern = r'container_cpu_usage_seconds_total\{[^}]*name="([^"]+)"[^}]*\}\s+([\d.e+]+)'
        
        for match in re.finditer(mem_pattern, text):
            name = match.group(1)
            val = float(match.group(2))
            if name not in containers: containers[name] = {}
            containers[name]['memory_bytes'] = val
            
        for match in re.finditer(cpu_pattern, text):
            name = match.group(1)
            val = float(match.group(2))
            if name not in containers: containers[name] = {}
            containers[name]['cpu_seconds'] = val
            
    except Exception as e:
        # logging.warning(f"Docker Metrics {ip_address}: {e}") # Silent fail if no metrics
        return []
    
    result = []
    for name, data in containers.items():
        if not name: continue
        # Basic heuristic for type
        c_type = 'db' if any(x in name for x in ['db', 'mongo', 'sql', 'redis', 'postgres', 'mariadb']) else 'app'
        
        result.append({
            'name': name,
            'memory_bytes': data.get('memory_bytes', 0),
            'cpu_seconds': data.get('cpu_seconds', 0),
            'type': c_type
        })
        
    return result
