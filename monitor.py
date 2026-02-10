"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Singleton Monitoring Daemon that periodically scrapes metrics from all enabled VPS
using a thread pool for concurrent collection.
"""

import threading
import time
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
import yaml

import db
import prometheus_metrics
import security_metrics


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MonitorDaemon:
    """
    Singleton daemon for continuous VPS monitoring.
    
    Runs in a background thread and scrapes metrics from all enabled VPS
    using parallel workers.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize daemon (only runs once due to singleton)."""
        if self._initialized:
            return
        
        self._initialized = True
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 60  # Default interval in seconds
        self._max_workers = 32
        
        # Load configuration
        self._load_config()
    
    def _load_config(self):
        """Load configuration from config.yaml and DB."""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    
                    monitoring = config.get('monitoring', {})
                    self._interval = monitoring.get('interval_seconds', 60)
                    self._max_workers = monitoring.get('max_workers', 32)
            
            # Override with DB config if available
            db_interval = db.get_config('monitoring_interval')
            if db_interval:
                self._interval = int(db_interval)
            
            logger.info(f"Monitor config: interval={self._interval}s, workers={self._max_workers}")
        
        except Exception as e:
            logger.error(f"Config loading error: {e}. Using defaults.")
    
    def start(self, interval: Optional[int] = None):
        """
        Start the monitoring daemon.
        
        Args:
            interval: Scraping interval in seconds (overrides config)
        """
        if self._running:
            logger.info("Daemon already running")
            return
        
        if interval:
            self._interval = interval
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MonitorDaemon")
        self._thread.start()
        
        logger.info(f"✓ Monitor daemon started (interval={self._interval}s)")
    
    def stop(self):
        """Stop the monitoring daemon gracefully."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        
        logger.info("Monitor daemon stopped")
    
    def _run_loop(self):
        """Main monitoring loop (runs in background thread)."""
        logger.info("Monitor loop started")
        
        while self._running:
            try:
                start_time = time.time()
                
                # Run collection cycle
                self._collect_all_metrics()
                
                # Calculate sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0, self._interval - elapsed)
                
                logger.info(f"Collection completed in {elapsed:.2f}s. Sleeping {sleep_time:.2f}s...")
                
                # Sleep in small chunks to allow quick shutdown
                sleep_chunks = int(sleep_time / 0.5)
                for _ in range(sleep_chunks):
                    if not self._running:
                        break
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Collection cycle error: {e}", exc_info=True)
                time.sleep(5)  # Brief pause before retrying
    
    def _collect_all_metrics(self):
        """
        Collect metrics from all enabled VPS using parallel workers.
        """
        # Get list of enabled VPS
        vps_list = db.list_vps(enabled_only=True)
        
        if not vps_list:
            logger.warning("No VPS configured for monitoring")
            return
        
        logger.info(f"Collecting metrics from {len(vps_list)} VPS...")
        
        # Adjust worker count based on VPS count
        worker_count = min(self._max_workers, len(vps_list), os.cpu_count() * 4 or 8)
        
        # Parallel collection with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            # Submit all VPS for scraping
            future_to_vps = {
                executor.submit(self._fetch_one, vps): vps
                for vps in vps_list
            }
            
            # Process results as they complete
            success_count = 0
            failure_count = 0
            
            for future in as_completed(future_to_vps):
                vps = future_to_vps[future]
                try:
                    result = future.result(timeout=15)
                    if result:
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    logger.error(f"Failed to collect from {vps['name']}: {e}")
                    failure_count += 1
        
        logger.info(f"Collection complete: {success_count} success, {failure_count} failed")
    
    def _fetch_one(self, vps: Dict[str, Any]) -> bool:
        """
        Fetch metrics from a single VPS and save to database.
        
        Args:
            vps: VPS dictionary from inventory
            
        Returns:
            True if successful, False otherwise
        """
        try:
            ip = vps['ip']
            name = vps['name']
            port = vps.get('port', 9100)
            cadvisor_port = vps.get('cadvisor_port', 8080)
            
            logger.debug(f"Scraping {name} ({ip})...")
            
            # Scrape metrics
            metrics = prometheus_metrics.scrape_vps(
                host=ip,
                node_port=port,
                cadvisor_port=cadvisor_port,
                include_docker=True
            )
            
            # Save to database
            success = db.save_status(
                vps_ip=ip,
                vps_name=name,
                status=metrics['status'],
                latency_ms=metrics.get('latency_ms'),
                cpu_percent=metrics.get('cpu_percent'),
                ram_percent=metrics.get('ram_percent'),
                disk_percent=metrics.get('disk_percent')
            )
            
            # Save Docker snapshot if available
            if metrics.get('docker_containers'):
                db.save_docker_snapshot(ip, metrics['docker_containers'])
            
            # 🔐 New: Collect Security State
            try:
                sec_state = security_metrics.collect_security_state(ip)
                if sec_state:
                    db.save_security_snapshot(ip, sec_state)
                    # Check for security alerts
                    try:
                        import alert
                        alert.check_and_alert_security(ip, name, sec_state)
                    except (ImportError, AttributeError):
                        pass
            except Exception as sec_e:
                logger.error(f"Security collection failed for {name}: {sec_e}")
            
            # Check for alerts (imported locally to avoid circular imports)
            try:
                import alert
                alert.check_and_alert(ip, name, metrics['status'])
            except ImportError:
                pass  # Alert module not yet available
            
            logger.debug(f"✓ {name}: {metrics['status']} (latency={metrics.get('latency_ms')}ms)")
            return success
        
        except Exception as e:
            logger.error(f"Error fetching {vps.get('name', vps.get('ip'))}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current daemon status."""
        return {
            'running': self._running,
            'interval': self._interval,
            'max_workers': self._max_workers,
            'thread_alive': self._thread.is_alive() if self._thread else False
        }
    
    def set_interval(self, interval: int):
        """Update monitoring interval."""
        if interval < 10:
            raise ValueError("Interval must be at least 10 seconds")
        
        self._interval = interval
        db.set_config('monitoring_interval', str(interval))
        logger.info(f"Interval updated to {interval}s")


# ========== CONVENIENCE FUNCTIONS ==========

_daemon_instance = None

def get_daemon() -> MonitorDaemon:
    """Get the singleton daemon instance."""
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = MonitorDaemon()
    return _daemon_instance


def start_daemon(interval: Optional[int] = None):
    """Start the monitoring daemon."""
    daemon = get_daemon()
    daemon.start(interval)


def stop_daemon():
    """Stop the monitoring daemon."""
    daemon = get_daemon()
    daemon.stop()


def get_daemon_status() -> Dict[str, Any]:
    """Get daemon status."""
    daemon = get_daemon()
    return daemon.get_status()
