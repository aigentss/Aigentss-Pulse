"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Prometheus metrics scraper for Node Exporter (System) and cAdvisor (Docker).
Supports exponential backoff retries and stealth port checking.
"""

import socket
import time
import logging
import threading
import httpx
import psutil
from typing import Dict, List, Optional, Any, Callable


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== STEALTH PORT CHECKING ==========

def is_port_open(host: str, port: int, timeout: int = 5) -> bool:
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


# ========== NODE EXPORTER SCRAPING ==========

def scrape_node_exporter(host: str, port: int = 9100, timeout: int = 5) -> Optional[Dict[str, Any]]:
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
            'disk_percent': float
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
            
            return {
                'status': 'UP',
                'latency_ms': round(latency_ms, 2),
                'cpu_percent': cpu_percent,
                'ram_percent': ram_percent,
                'disk_percent': disk_percent
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

def scrape_cadvisor(host: str, port: int = 8080, timeout: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Scrape Docker container metrics from cAdvisor.
    
    Args:
        host: IP address of the VPS
        port: cAdvisor port (default 8080)
        timeout: HTTP timeout in seconds
        
    Returns:
        List of container metrics: [
            {
                'name': str,
                'cpu_percent': float,
                'memory_mb': float,
                'memory_limit_mb': float
            },
            ...
        ]
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
            return _parse_container_metrics(metrics_text, host)
    
    return retry_with_backoff(_fetch, max_attempts=2, base_delay=1.0)


# Global state for Docker CPU rate calculation
# Format: {vps_ip: {container_name: (timestamp, cpu_seconds)}}
_DOCKER_CPU_CACHE = {}
_CACHE_LOCK = threading.Lock()

def _parse_container_metrics(metrics_text: str, host: str) -> List[Dict[str, Any]]:
    """
    Parse cAdvisor metrics with correct per-container isolation.
    CRITICAL FIX: Uses container ID as unique key to avoid aggregating system totals.
    """
    containers_by_id = {}  # Use ID as key to ensure uniqueness
    current_time = time.time()
    
    try:
        num_cores = psutil.cpu_count(logical=True) or 4
        logger.debug(f"Parsing container metrics with {num_cores} CPU cores detected")
        
        # FIRST PASS: Parse all metric lines and store by container ID
        for line in metrics_text.split('\n'):
            if not line or line.startswith('#'):
                continue
            
            # Only process container CPU and memory metrics
            is_cpu = 'container_cpu_usage_seconds_total{' in line
            is_mem = 'container_memory_working_set_bytes{' in line
            
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
            
            # For CPU metrics, skip per-core breakdowns (only aggregate)
            if is_cpu and 'cpu=' in line and 'cpu="total"' not in line:
                continue
            
            # Parse the metric value
            try:
                value = float(line.split()[-1])
            except (ValueError, IndexError):
                logger.warning(f"Could not parse value from line: {line[:100]}")
                continue
            
            # Initialize container entry if needed
            if container_id not in containers_by_id:
                containers_by_id[container_id] = {
                    'id': container_id,
                    'name': name,
                    'image': image,
                    'cpu_seconds': 0.0,
                    'memory_bytes': 0.0
                }
            
            # Store the metric value
            if is_cpu:
                # Only update if this is a higher value (handles duplicate lines)
                if value > containers_by_id[container_id]['cpu_seconds']:
                    containers_by_id[container_id]['cpu_seconds'] = value
            elif is_mem:
                # Only update if this is a higher value
                if value > containers_by_id[container_id]['memory_bytes']:
                    containers_by_id[container_id]['memory_bytes'] = value
        
        logger.debug(f"Found {len(containers_by_id)} unique containers")
        
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
                    cache_key = f"{name}_{container_id}"  # Unique key per container
                    
                    if cache_key in host_cache:
                        prev_time, prev_cpu = host_cache[cache_key]
                        time_delta = current_time - prev_time
                        cpu_delta = cpu_seconds - prev_cpu
                        
                        if time_delta > 0.5:  # Minimum sample interval
                            if cpu_delta < 0:
                                # Container restarted
                                logger.info(f"Container {name} ({container_id[:12]}) restarted")
                                host_cache[cache_key] = (current_time, cpu_seconds)
                            elif cpu_delta >= 0:
                                # Calculate CPU usage as percentage of ONE core
                                # cpu_delta is in seconds, time_delta is also in seconds
                                # cores_used = cpu_delta / time_delta
                                # For single-core representation: percentage = cores_used * 100
                                cores_used = cpu_delta / time_delta
                                raw_pct = cores_used * 100.0
                                
                                # Cap at 100% (full utilization of one core)
                                cpu_pct = min(raw_pct, 100.0)
                                cpu_pct = max(0.0, cpu_pct)  # Ensure non-negative
                                cpu_pct = round(cpu_pct, 2)
                                
                                logger.debug(f"{name}: cpu_delta={cpu_delta:.4f}s, time_delta={time_delta:.2f}s, final={cpu_pct}%")
                    
                    # Update cache for next cycle
                    host_cache[cache_key] = (current_time, cpu_seconds)
                
                # Convert memory to MB
                memory_mb = round(mem_bytes / (1024 * 1024), 2)
                
                result.append({
                    'name': name,
                    'cpu_percent': cpu_pct,
                    'memory_mb': memory_mb,
                    'status': 'RUNNING'
                })
        
        logger.info(f"Parsed {len(result)} containers from {host}")
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
        docker_metrics = scrape_cadvisor(host, cadvisor_port)
        result['docker_containers'] = docker_metrics if docker_metrics else []
    else:
        result['docker_containers'] = []
    
    return result
