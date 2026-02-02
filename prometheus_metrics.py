"""
Prometheus Node Exporter Metrics Fetcher
Fetches CPU, RAM, and Disk usage from prometheus-node-exporter endpoints.
"""

import requests
import re
import logging

def get_node_metrics(ip_address, port=9100, timeout=2):
    """
    Fetches system metrics from a Prometheus Node Exporter endpoint.
    
    Args:
        ip_address: Target IP address
        port: Node Exporter port (default 9100)
        timeout: Request timeout in seconds
    
    Returns:
        dict with keys: cpu, ram, disk (percentage values)
    """
    metrics = {'cpu': 0, 'ram': 0, 'disk': 0}
    
    try:
        url = f"http://{ip_address}:{port}/metrics"
        response = requests.get(url, timeout=timeout)
        
        if response.status_code != 200:
            logging.warning(f"Node Exporter {ip_address}: HTTP {response.status_code}")
            return metrics
        
        text = response.text
        
        # --- CPU Usage ---
        # Calculate from node_cpu_seconds_total (sum all idle across cores)
        # Formula: 100 - (sum_idle / sum_total) * 100
        cpu_idle_matches = re.findall(r'node_cpu_seconds_total\{[^}]*mode="idle"[^}]*\}\s+([\d.]+)', text)
        cpu_total_matches = re.findall(r'node_cpu_seconds_total\{[^}]*\}\s+([\d.]+)', text)
        
        if cpu_idle_matches and cpu_total_matches:
            idle_seconds = sum(float(m) for m in cpu_idle_matches)
            total_seconds = sum(float(m) for m in cpu_total_matches)
            if total_seconds > 0:
                idle_pct = (idle_seconds / total_seconds) * 100
                metrics['cpu'] = round(100 - idle_pct, 1)
        
        # --- RAM Usage ---
        mem_total_match = re.search(r'node_memory_MemTotal_bytes\s+([\d.e+]+)', text)
        mem_avail_match = re.search(r'node_memory_MemAvailable_bytes\s+([\d.e+]+)', text)
        
        if mem_total_match and mem_avail_match:
            total = float(mem_total_match.group(1))
            available = float(mem_avail_match.group(1))
            if total > 0:
                used_pct = ((total - available) / total) * 100
                metrics['ram'] = round(used_pct, 1)
        
        # --- Disk Usage (root filesystem) ---
        # Look for mountpoint="/"
        disk_size_match = re.search(r'node_filesystem_size_bytes\{.*mountpoint="/",.*\}\s+([\d.e+]+)', text)
        disk_avail_match = re.search(r'node_filesystem_avail_bytes\{.*mountpoint="/",.*\}\s+([\d.e+]+)', text)
        
        # Fallback: try without explicit mountpoint filter (first match)
        if not disk_size_match:
            disk_size_match = re.search(r'node_filesystem_size_bytes\{.*fstype="ext4".*\}\s+([\d.e+]+)', text)
            disk_avail_match = re.search(r'node_filesystem_avail_bytes\{.*fstype="ext4".*\}\s+([\d.e+]+)', text)
        
        if disk_size_match and disk_avail_match:
            size = float(disk_size_match.group(1))
            avail = float(disk_avail_match.group(1))
            if size > 0:
                used_pct = ((size - avail) / size) * 100
                metrics['disk'] = round(used_pct, 1)
        
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
