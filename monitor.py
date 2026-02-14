"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c.
Date: 2026-02-14
Propietario: Ing. Ángel David Yaguana, Dr. h.c.

Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
PROPRIETARY AND CONFIDENTIAL.

Central Monitoring Daemon (Singleton).

ARCHITECTURAL DECISION:
- Runs as a background thread within the main process to simplify deployment (no separate worker process needed).
- Uses a ThreadPoolExecutor to scrape multiple VPS nodes concurrently (`max_workers=32`).
- Implements 'Auto-Healing' by triggering `db_cleanup_metrics.deep_clean()` on startup and error spikes.
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
import db_cleanup_metrics


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
        
        # Run deep clean on startup to ensure data integrity
        try:
             db_cleanup_metrics.deep_clean()
        except Exception as e:
             logger.error(f"Startup DB cleanup failed: {e}")
        
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
                # Auto-heal attempt on error
                try:
                    db_cleanup_metrics.deep_clean()
                except:
                    pass
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
            
            # Gap Detection: Check if last status is stale
            now = int(time.time())
            last_status = db.get_latest_status(ip)
            
            if last_status and (now - last_status['timestamp'] > self._interval + 10):
                logger.warning(f"Gap detected for {name}: {now - last_status['timestamp']}s since last update (threshold: {self._interval + 10}s)")
                # Mark as DOWN due to gap
                db.save_status(ip, name, 'DOWN')
                # Trigger alert
                try:
                    import alert
                    alert.check_and_alert(ip, name, 'DOWN')
                except ImportError:
                    pass
            
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
            
            # AUTOMATIC HARDWARE SYNC: Update VPS capacity if detected
            # This fixes the issue where default 4 cores / 8GB RAM are used for calculations
            if metrics.get('hardware'):
                hw = metrics['hardware']
                if hw.get('cpu_cores') or hw.get('ram_gb') or hw.get('disk_gb'):
                    db.update_vps_hardware(
                        ip, 
                        max_cpu_cores=hw.get('cpu_cores'),
                        max_ram_gb=hw.get('ram_gb'),
                        max_disk_gb=hw.get('disk_gb')
                    )
                    logger.info(f"Updated HW for {name}: {hw}")
            
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
