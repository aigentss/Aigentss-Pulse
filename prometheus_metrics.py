"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Scraping Logic for Prometheus Endpoints.

ARCHITECTURAL DECISION:
- Custom parser instead of `prometheus_client` library to handle specific 'cAdvisor' format inconsistencies (spaces, timestamps).
- Enforces strict regex validation `r'\s+([\d.eE+-]+)(?:\s+\d+)?$'` to reject corrupt data.
- Applies immediate sanity checks (CPU > N*100%, RAM > 128GB) at the ingestion layer.
"""

import socket
import time
import httpx
import re
import threading
import logging
import psutil
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== STEALTH PORT CHECKING ==========

def is_port_open(host: str, port: int, timeout: int = 10) -> bool:
    """
    Stealth check if a port is open before attempting HTTP connection.
    
    Args:
        host: IP address or hostname
        port: Port number
        timeout: Connection timeout in seconds
        
    Returns:
        True if port is open, False otherwise
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
        return False


# ========== RETRY LOGIC ==========

def retry_with_backoff(func, max_attempts: int = 3, base_delay: float = 1.0):
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Callable to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds (doubles each retry)
        
    Returns:
        Function result or None if all attempts fail
    """
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"All {max_attempts} attempts failed: {e}")
                return None


# ========== HARDWARE DETECTION ==========

def _parse_hardware_info(metrics_text: str) -> Dict[str, Any]:
    """
    Extract hardware specifications from Node Exporter metrics.
    Returns:
        {
            'cpu_cores': int,
            'ram_gb': float,
            'disk_gb': float
        }
    """
    info = {}
    try:
        import re
        
        # 1. Detect CPU Cores (count unique 'cpu' labels)
        # metric: node_cpu_seconds_total{cpu="0",mode="idle"}
        cpu_matches = re.findall(r'node_cpu_seconds_total\{[^}]*cpu="(\d+)"', metrics_text)
        if cpu_matches:
            # Count unique CPU IDs
            unique_cpus = set(cpu_matches)
            info['cpu_cores'] = len(unique_cpus)
        else:
            # Fallback for some node_exporter versions
            core_match = re.search(r'machine_cpu_cores\s+(\d+)', metrics_text)
            if core_match:
                info['cpu_cores'] = int(core_match.group(1))

        # 2. Detect Total RAM
        # metric: node_memory_MemTotal_bytes 2.5123e+10
        mem_match = re.search(r'node_memory_MemTotal_bytes\s+([\d.e+]+)', metrics_text)
        if mem_match:
            bytes_val = float(mem_match.group(1))
            info['ram_gb'] = round(bytes_val / (1024**3), 2)  # Convert to GB
            
        # 3. Detect Total Disk (Root)
        # metric: node_filesystem_size_bytes{mountpoint="/"} 
        disk_match = re.search(r'node_filesystem_size_bytes\{[^}]*mountpoint="/"[^}]*\}\s+([\d.e+]+)', metrics_text)
        if not disk_match:
             disk_match = re.search(r'node_filesystem_size_bytes\{[^}]*fstype="ext4"[^}]*\}\s+([\d.e+]+)', metrics_text)
             
        if disk_match:
            bytes_val = float(disk_match.group(1))
            info['disk_gb'] = round(bytes_val / (1024**3), 2) # Convert to GB
            
    except Exception as e:
        logger.warning(f"Hardware detection error: {e}")
    
    return info


# ========== NODE EXPORTER SCRAPING ==========

def scrape_node_exporter(host: str, port: int = 9100, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    Scrape system metrics from Node Exporter.
    
    Args:
        host: IP address of the VPS
        port: Node Exporter port (default 9100)
        timeout: HTTP timeout in seconds
        
    Returns:
        Dictionary with metrics: {
            'status': 'UP' | 'DOWN',
            'latency_ms': float,
            'cpu_percent': float,
            'ram_percent': float,
            'disk_percent': float,
            'hardware': { ... }  # Added hardware info
        }
    """
    # Stealth check
    if not is_port_open(host, port, timeout):
        return {
            'status': 'DOWN',
            'latency_ms': None,
            'cpu_percent': None,
            'ram_percent': None,
            'disk_percent': None
        }
    
    def _fetch():
        start_time = time.time()
        url = f"http://{host}:{port}/metrics"
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            
            latency_ms = (time.time() - start_time) * 1000
            metrics_text = response.text
            
            # Parse metrics
            cpu_percent = _parse_cpu_usage(metrics_text)
            ram_percent = _parse_memory_usage(metrics_text)
            disk_percent = _parse_disk_usage(metrics_text)
            
            # Detect hardware info
            hardware = _parse_hardware_info(metrics_text)
            
            return {
                'status': 'UP',
                'latency_ms': round(latency_ms, 2),
                'cpu_percent': cpu_percent,
                'ram_percent': ram_percent,
                'disk_percent': disk_percent,
                'hardware': hardware
            }
    
    return retry_with_backoff(_fetch, max_attempts=3, base_delay=1.0)


def _parse_cpu_usage(metrics_text: str) -> Optional[float]:
    """
    Calculate CPU usage from node_cpu_seconds_total.
    Formula: 100 - (sum_idle / sum_total) * 100
    """
    try:
        import re
        
        # Extract all idle CPU seconds
        idle_matches = re.findall(r'node_cpu_seconds_total\{[^}]*mode="idle"[^}]*\}\s+([\d.]+)', metrics_text)
        # Extract all total CPU seconds
        total_matches = re.findall(r'node_cpu_seconds_total\{[^}]*\}\s+([\d.]+)', metrics_text)
        
        if idle_matches and total_matches:
            idle_seconds = sum(float(m) for m in idle_matches)
            total_seconds = sum(float(m) for m in total_matches)
            
            if total_seconds > 0:
                idle_pct = (idle_seconds / total_seconds) * 100
                cpu_usage = 100 - idle_pct
                # Clamp to valid range
                return round(max(0.0, min(100.0, cpu_usage)), 2)
        
        return None
    except Exception as e:
        logger.warning(f"CPU parsing error: {e}")
        return None


def _parse_memory_usage(metrics_text: str) -> Optional[float]:
    """Calculate RAM usage percentage from available/total memory."""
    try:
        import re
        
        mem_total_match = re.search(r'node_memory_MemTotal_bytes\s+([\d.e+]+)', metrics_text)
        mem_avail_match = re.search(r'node_memory_MemAvailable_bytes\s+([\d.e+]+)', metrics_text)
        
        if mem_total_match and mem_avail_match:
            total = float(mem_total_match.group(1))
            available = float(mem_avail_match.group(1))
            
            if total > 0:
                used_pct = ((total - available) / total) * 100
                # Clamp to valid range
                return round(max(0.0, min(100.0, used_pct)), 2)
        
        return None
    except Exception as e:
        logger.warning(f"Memory parsing error: {e}")
        return None


def _parse_disk_usage(metrics_text: str) -> Optional[float]:
    """Calculate disk usage percentage for root filesystem."""
    try:
        import re
        
        # Try to find root filesystem first
        disk_size_match = re.search(r'node_filesystem_size_bytes\{[^}]*mountpoint="/"[^}]*\}\s+([\d.e+]+)', metrics_text)
        disk_avail_match = re.search(r'node_filesystem_avail_bytes\{[^}]*mountpoint="/"[^}]*\}\s+([\d.e+]+)', metrics_text)
        
        # Fallback: try ext4 filesystem
        if not disk_size_match:
            disk_size_match = re.search(r'node_filesystem_size_bytes\{[^}]*fstype="ext4"[^}]*\}\s+([\d.e+]+)', metrics_text)
            disk_avail_match = re.search(r'node_filesystem_avail_bytes\{[^}]*fstype="ext4"[^}]*\}\s+([\d.e+]+)', metrics_text)
        
        if disk_size_match and disk_avail_match:
            size = float(disk_size_match.group(1))
            avail = float(disk_avail_match.group(1))
            
            if size > 0:
                used_pct = ((size - avail) / size) * 100
                # Clamp to valid range
                return round(max(0.0, min(100.0, used_pct)), 2)
        
        return None
    except Exception as e:
        logger.warning(f"Disk parsing error: {e}")
        return None


# ========== CADVISOR SCRAPING (DOCKER METRICS) ==========

def scrape_cadvisor(host: str, port: int = 8080, timeout: int = 10, num_cores: int = 1, total_ram_gb: Optional[float] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Scrape Docker container metrics from cAdvisor.
    
    Args:
        host: IP address of the VPS
        port: cAdvisor port (default 8080)
        timeout: HTTP timeout in seconds
        num_cores: Number of CPU cores on the host (for % calc)
        total_ram_gb: Total RAM of the host in GB (for sanity checks)
        
    Returns:
        List of container metrics
    """
    # Stealth check
    if not is_port_open(host, port, timeout):
        logger.info(f"cAdvisor not available on {host}:{port}")
        return None
    
    def _fetch():
        url = f"http://{host}:{port}/metrics"
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            
            metrics_text = response.text
            return _parse_container_metrics(metrics_text, host, num_cores, total_ram_gb)
    
    return retry_with_backoff(_fetch, max_attempts=2, base_delay=1.0)


# Global state for Docker CPU rate calculation
# Format: {vps_ip: {container_name: (timestamp, cpu_seconds)}}
_DOCKER_CPU_CACHE = {}
_CACHE_LOCK = threading.Lock()

def _parse_container_metrics(metrics_text: str, host: str, num_cores: int = 1, total_ram_gb: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Parse cAdvisor metrics with correct per-container isolation and CPU rate calculation.
    
    Args:
        metrics_text: Raw Prometheus metrics
        host: Host IP (for caching state)
        num_cores: Total CPU cores on the host
        total_ram_gb: Total RAM in GB (for validation)
    """
    containers_by_id = {}  # Use ID as key to ensure uniqueness
    current_time = time.time()
    
    # Ensure at least 1 core to avoid division by zero
    num_cores = max(1, num_cores)
    
    # Validation limit for memory (default to 64GB if unknown, or 2x physical RAM)
    # We set a hard cap of 128GB for a VPS context to catch the 1.6TB bug
    max_valid_ram_bytes = (total_ram_gb * 1024**3 * 1.5) if total_ram_gb else (128 * 1024**3) # 128GB default cap
    
    try:
        logger.debug(f"Parsing container metrics for {host}. Max valid RAM: {max_valid_ram_bytes/1024**3:.1f} GB")
        
        # FIRST PASS: Parse all metric lines and store by container ID
        for line in metrics_text.split('\n'):
            if not line or line.startswith('#'):
                continue
            
            # Only process container CPU and memory metrics
            is_cpu = 'container_cpu_usage_seconds_total{' in line
            is_mem = 'container_memory_usage_bytes{' in line
            
            if not (is_cpu or is_mem):
                continue
                
            if 'name=' not in line:
                continue
            
            # Extract all labels from the metric line
            labels = _extract_all_labels(line)
            name = labels.get('name', '')
            image = labels.get('image', '')
            container_id = labels.get('id', '')
            
            # Skip system containers and empty entries
            if not name or name in ['/', 'POD'] or not image or not container_id:
                continue
            
            # For CPU metrics, ONLY accept the aggregate with cpu="total"
            if is_cpu:
                cpu_label = labels.get('cpu', '')
                if cpu_label != 'total':
                    continue
            
            # Memory metric selection (prefer most specific)
            if is_mem:
                num_labels = len(labels)
                if container_id in containers_by_id:
                    current_entry = containers_by_id[container_id]
                    current_label_count = current_entry.get('_label_count', 999)
                    if num_labels >= current_label_count:
                        continue
            else:
                num_labels = 999
            
            # ROBUST PARSING: Use Regex to extract value and ignore potential timestamp
            # This Regex looks for: [Space] [Value] [Optional Space] [Optional Timestamp] [End of Line]
            # It explicitly avoids matching the timestamp as the value.
            match = re.search(r'\s+([\d.eE+-]+)(?:\s+\d+)?$', line)
            
            if match:
                try:
                    raw_val = float(match.group(1))
                    
                    # === SANITY CHECKS (The "Anti-Gravity" Logic) ===
                    
                    if is_mem:
                        # Check: Memory > Max Limit (e.g. 1.6TB bug)
                        if raw_val > max_valid_ram_bytes:
                            # Log only once per scrape per container to avoid spam
                            # logger.warning(f"Sanity: Dropped memory outlier {raw_val/1024**3:.1f}GB for {name}")
                            continue
                        value = raw_val
                        
                    elif is_cpu:
                        # Check: CPU Seconds > impossibly high number implies corruption or bad parsing
                        # But seconds is cumulative, so it can be high. 
                        # We rely on the DELTA calculation later to filter bad rates.
                        # However, if we see "98000%" in rate, that's handled in the rate calc.
                        value = raw_val
                    else:
                        value = raw_val
                        
                except ValueError:
                    continue
            else:
                continue

            # Initialize container entry if needed
            if container_id not in containers_by_id:
                containers_by_id[container_id] = {
                    'id': container_id,
                    'name': name,
                    'image': image,
                    'cpu_seconds': 0.0,
                    'memory_bytes': 0.0,
                    '_label_count': 999 
                }
            
            # Store the metric value
            if is_cpu:
                if value > containers_by_id[container_id]['cpu_seconds']:
                    containers_by_id[container_id]['cpu_seconds'] = value
            elif is_mem:
                containers_by_id[container_id]['memory_bytes'] = value
                containers_by_id[container_id]['_label_count'] = num_labels
        
        # SECOND PASS: Calculate CPU percentages using cache
        with _CACHE_LOCK:
            if host not in _DOCKER_CPU_CACHE:
                _DOCKER_CPU_CACHE[host] = {}
            
            host_cache = _DOCKER_CPU_CACHE[host]
            result = []
            
            for container_id, stats in containers_by_id.items():
                cpu_seconds = stats['cpu_seconds']
                mem_bytes = stats['memory_bytes']
                name = stats['name']
                cpu_pct = 0.0
                
                # Calculate CPU percentage
                if cpu_seconds > 0:
                    cache_key = f"{name}_{container_id}"
                    
                    if cache_key in host_cache:
                        prev_time, prev_cpu = host_cache[cache_key]
                        time_delta = current_time - prev_time
                        cpu_delta = cpu_seconds - prev_cpu
                        
                        if time_delta > 0.5:
                            if cpu_delta < 0:
                                # Container restarted
                                host_cache[cache_key] = (current_time, cpu_seconds)
                            elif cpu_delta >= 0:
                                # FORMULA: (Delta CPU Seconds / (Delta Time * Cores)) * 100
                                cores_used = cpu_delta / time_delta
                                raw_pct = (cores_used / num_cores) * 100.0
                                
                                # SANITY CHECK FOR CPU %
                                # Even with 100 cores, 10,000% is unlikely. 
                                # cAdvisor bug can return massive spikes.
                                if raw_pct > (num_cores * 100 * 2): # allow 2x burst
                                    # logger.warning(f"Sanity: Dropped CPU spike {raw_pct:.1f}% for {name}")
                                    cpu_pct = 0.0 # Ignore spike
                                else:
                                    cpu_pct = min(raw_pct, num_cores * 100.0) # Cap at max theoretical
                                    cpu_pct = round(cpu_pct, 2)
                    
                    # Update cache
                    host_cache[cache_key] = (current_time, cpu_seconds)
                
                # Convert memory to MB (Bytes -> MB)
                memory_mb = round(mem_bytes / (1024 * 1024), 2)
                
                result.append({
                    'name': name,
                    'cpu_percent': cpu_pct,
                    'memory_mb': memory_mb,
                    'status': 'RUNNING'
                })
        
        return result
    
    except Exception as e:
        logger.error(f"Container metrics parsing error: {e}", exc_info=True)
        return []

def _extract_all_labels(line: str) -> Dict[str, str]:
    """Extract all labels from a Prometheus metric line into a dict."""
    labels = {}
    try:
        if '{' not in line or '}' not in line:
            return labels
        
        label_str = line.split('{')[1].split('}')[0]
        # Regex to handle quoted values with commas
        # e.g. name="foo,bar",id="123"
        import re
        matches = re.finditer(r'([a-zA-Z0-9_]+)="([^"]*)"', label_str)
        for m in matches:
            labels[m.group(1)] = m.group(2)
    except Exception:
        pass
    return labels

def _extract_label_value(line: str, label: str) -> Optional[str]:
    """Simple extractor for single label (kept for backward compat or quick checks)."""
    labels = _extract_all_labels(line)
    return labels.get(label)

# Combined scraping logic


# ========== COMBINED SCRAPING FUNCTION ==========

def scrape_vps(
    host: str,
    node_port: int = 9100,
    cadvisor_port: int = 8080,
    include_docker: bool = True
) -> Dict[str, Any]:
    """
    Scrape all available metrics from a VPS.
    
    Args:
        host: IP address of the VPS
        node_port: Node Exporter port
        cadvisor_port: cAdvisor port
        include_docker: Whether to attempt Docker metrics scraping
        
    Returns:
        Combined metrics dictionary with system and Docker data
    """
    # Get system metrics
    system_metrics = scrape_node_exporter(host, node_port)
    
    if not system_metrics:
        system_metrics = {
            'status': 'DOWN',
            'latency_ms': None,
            'cpu_percent': None,
            'ram_percent': None,
            'disk_percent': None
        }
    
    result = {
        'host': host,
        'timestamp': int(time.time()),
        **system_metrics
    }
    
    # Get Docker metrics if requested and system is UP
    if include_docker and system_metrics['status'] == 'UP':
        # Use detected CPU cores for accurate container % calculation
        num_cores = 1
        total_ram_gb = None
        
        if 'hardware' in system_metrics:
            hw = system_metrics['hardware']
            if 'cpu_cores' in hw:
                num_cores = hw['cpu_cores']
            if 'ram_gb' in hw:
                total_ram_gb = hw['ram_gb']
            
        docker_metrics = scrape_cadvisor(host, cadvisor_port, timeout=10, num_cores=num_cores, total_ram_gb=total_ram_gb)
        result['docker_containers'] = docker_metrics if docker_metrics else []
    else:
        result['docker_containers'] = []
    
    return result
