"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Database layer providing SQLite persistence with WAL mode and optimized PRAGMAs.
Handles two dedicated databases:
1. aigents_pulse.db: System metadata, VPS inventory, and alerts.
2. aigents_dockers_vps.db: Dedicated Docker container metric history.
"""

import sqlite3
import json
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# Database paths
BASE_DIR = Path(__file__).parent
SYSTEM_DB_PATH = BASE_DIR / "aigents_pulse.db"
DOCKER_DB_PATH = BASE_DIR / "aigents_dockers_vps.db"


@contextmanager
def get_connection(db_type: str = "system"):
    """
    Context manager for database connections with WAL mode and foreign keys.
    Args:
        db_type: Either 'system' or 'docker' to select the database.
    """
    db_path = SYSTEM_DB_PATH if db_type == "system" else DOCKER_DB_PATH
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        # Enable foreign keys and WAL mode for every connection
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialize both system and docker databases with optimized schemas.
    """
    # 1. Initialize System Database
    with get_connection("system") as conn:
        conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        
        # Status history table (System Metrics)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vps_ip TEXT NOT NULL,
                vps_name TEXT,
                timestamp INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('UP', 'DOWN')),
                latency_ms REAL,
                cpu_percent REAL,
                ram_percent REAL,
                disk_percent REAL,
                UNIQUE(vps_ip, timestamp)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status_history_lookup ON status_history(vps_ip, timestamp DESC)")
        
        # VPS inventory table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vps_inventory (
                ip TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                port INTEGER DEFAULT 9100,
                cadvisor_port INTEGER DEFAULT 8080,
                enabled BOOLEAN DEFAULT 1,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        # Migration: Add hardware capacity columns (v3.1 enhancement)
        try:
            conn.execute("ALTER TABLE vps_inventory ADD COLUMN max_cpu_cores INTEGER DEFAULT 4")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            conn.execute("ALTER TABLE vps_inventory ADD COLUMN max_ram_gb REAL DEFAULT 8.0")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            conn.execute("ALTER TABLE vps_inventory ADD COLUMN max_disk_gb REAL DEFAULT 100.0")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Configuration key-value store
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        # Alert state tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                vps_ip TEXT PRIMARY KEY,
                last_status TEXT NOT NULL CHECK(last_status IN ('UP', 'DOWN')),
                last_alert_timestamp INTEGER,
                last_security_hash TEXT,
                FOREIGN KEY(vps_ip) REFERENCES vps_inventory(ip) ON DELETE CASCADE
            )
        """)

        # Migration: Ensure last_security_hash column exists for v3.0 -> v3.1 upgrades
        try:
            conn.execute("ALTER TABLE alert_state ADD COLUMN last_security_hash TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Security snapshots
        conn.execute("""
            CREATE TABLE IF NOT EXISTS security_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vps_ip TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                security_json TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_security_snapshots_lookup ON security_snapshots(vps_ip, timestamp DESC)")

    # 2. Initialize Docker Database
    with get_connection("docker") as conn:
        conn.execute("PRAGMA cache_size=-64000;")
        
        # Docker container snapshots (Historical performance)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS docker_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vps_ip TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                containers_json TEXT NOT NULL
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docker_snapshots_lookup ON docker_snapshots(vps_ip, timestamp DESC)")


# ========== SYSTEM STATUS OPERATIONS ==========

def save_status(vps_ip: str, vps_name: str, status: str, latency_ms: Optional[float] = None, 
                cpu_percent: Optional[float] = None, ram_percent: Optional[float] = None, 
                disk_percent: Optional[float] = None) -> bool:
    """Save system metrics snapshot to the system database."""
    # Clamp metrics to valid ranges (0-100%)
    if cpu_percent is not None:
        cpu_percent = max(0.0, min(100.0, cpu_percent))
    if ram_percent is not None:
        ram_percent = max(0.0, min(100.0, ram_percent))
    if disk_percent is not None:
        disk_percent = max(0.0, min(100.0, disk_percent))
    
    timestamp = int(time.time())
    with get_connection("system") as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO status_history 
            (vps_ip, vps_name, timestamp, status, latency_ms, cpu_percent, ram_percent, disk_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (vps_ip, vps_name, timestamp, status, latency_ms, cpu_percent, ram_percent, disk_percent))
        return cursor.rowcount > 0

def get_last_24h(vps_ip: str) -> List[Dict[str, Any]]:
    """Retrieve last 24h of system metrics for graph generation."""
    cutoff_time = int(time.time()) - (24 * 3600)
    with get_connection("system") as conn:
        cursor = conn.execute("""
            SELECT timestamp, status, latency_ms, cpu_percent, ram_percent, disk_percent
            FROM status_history
            WHERE vps_ip = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (vps_ip, cutoff_time))
        return [dict(row) for row in cursor.fetchall()]

def get_latest_status(vps_ip: str) -> Optional[Dict[str, Any]]:
    """Get most recent status snapshot."""
    with get_connection("system") as conn:
        cursor = conn.execute("SELECT * FROM status_history WHERE vps_ip = ? ORDER BY timestamp DESC LIMIT 1", (vps_ip,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_history(vps_ip: Optional[str] = None, start_time: Optional[int] = None, 
                end_time: Optional[int] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    """General query for status history."""
    query = "SELECT * FROM status_history WHERE 1=1"
    params = []
    if vps_ip:
        query += " AND vps_ip = ?"; params.append(vps_ip)
    if start_time:
        query += " AND timestamp >= ?"; params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"; params.append(end_time)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    with get_connection("system") as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# ========== DOCKER OPERATIONS ==========

def save_docker_snapshot(vps_ip: str, containers: List[Dict[str, Any]]) -> None:
    """Save Docker metrics to the dedicated docker database."""
    timestamp = int(time.time())
    containers_json = json.dumps(containers)
    with get_connection("docker") as conn:
        conn.execute("""
            INSERT INTO docker_snapshots (vps_ip, timestamp, containers_json)
            VALUES (?, ?, ?)
        """, (vps_ip, timestamp, containers_json))

def get_latest_docker_snapshot(vps_ip: str) -> Optional[List[Dict[str, Any]]]:
    """Get the most recent Docker performance snapshot."""
    with get_connection("docker") as conn:
        cursor = conn.execute("SELECT containers_json FROM docker_snapshots WHERE vps_ip = ? ORDER BY timestamp DESC LIMIT 1", (vps_ip,))
        row = cursor.fetchone()
        return json.loads(row["containers_json"]) if row else None

def get_docker_history(vps_ip: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve historical Docker snapshots for specific VPS."""
    with get_connection("docker") as conn:
        cursor = conn.execute("SELECT * FROM docker_snapshots WHERE vps_ip = ? ORDER BY timestamp DESC LIMIT ?", (vps_ip, limit))
        return [dict(row) for row in cursor.fetchall()]


# ========== SECURITY OPERATIONS ==========

def save_security_snapshot(vps_ip: str, security_dict: Dict[str, Any]) -> None:
    """Save Security audit snapshot to the system database."""
    timestamp = int(time.time())
    security_json = json.dumps(security_dict)
    with get_connection("system") as conn:
        conn.execute("""
            INSERT INTO security_snapshots (vps_ip, timestamp, security_json)
            VALUES (?, ?, ?)
        """, (vps_ip, timestamp, security_json))

def get_latest_security_snapshot(vps_ip: str) -> Optional[Dict[str, Any]]:
    """Get the most recent Security audit snapshot."""
    with get_connection("system") as conn:
        cursor = conn.execute("SELECT security_json FROM security_snapshots WHERE vps_ip = ? ORDER BY timestamp DESC LIMIT 1", (vps_ip,))
        row = cursor.fetchone()
        return json.loads(row["security_json"]) if row else None

def get_security_history(vps_ip: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve historical security snapshots."""
    with get_connection("system") as conn:
        cursor = conn.execute("SELECT * FROM security_snapshots WHERE vps_ip = ? ORDER BY timestamp DESC LIMIT ?", (vps_ip, limit))
        return [dict(row) for row in cursor.fetchall()]


# ========== INVENTORY & CONFIG & ALERTS (System DB) ==========

def add_vps(ip: str, name: str, port: int = 9100, cadvisor_port: int = 8080,
            max_cpu_cores: Optional[int] = None, max_ram_gb: Optional[float] = None, 
            max_disk_gb: Optional[float] = None) -> bool:
    """Add VPS to inventory with optional hardware capacity limits."""
    with get_connection("system") as conn:
        try:
            conn.execute("""
                INSERT INTO vps_inventory (ip, name, port, cadvisor_port, max_cpu_cores, max_ram_gb, max_disk_gb) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ip, name, port, cadvisor_port, max_cpu_cores or 4, max_ram_gb or 8.0, max_disk_gb or 100.0))
            return True
        except sqlite3.IntegrityError: return False

def update_vps(ip: str, name: Optional[str] = None, enabled: Optional[bool] = None) -> bool:
    """Update VPS inventory entry."""
    updates = []; params = []
    if name is not None: updates.append("name = ?"); params.append(name)
    if enabled is not None: updates.append("enabled = ?"); params.append(1 if enabled else 0)
    if not updates: return False
    updates.append("updated_at = ?"); params.append(int(time.time()))
    params.append(ip)
    query = f"UPDATE vps_inventory SET {', '.join(updates)} WHERE ip = ?"
    with get_connection("system") as conn:
        cursor = conn.execute(query, params)
        return cursor.rowcount > 0

def update_vps_hardware(ip: str, max_cpu_cores: Optional[int] = None, 
                       max_ram_gb: Optional[float] = None, 
                       max_disk_gb: Optional[float] = None) -> bool:
    """Update VPS hardware capacity limits."""
    with get_connection("system") as conn:
        updates = []
        params = []
        if max_cpu_cores is not None:
            updates.append("max_cpu_cores = ?")
            params.append(max_cpu_cores)
        if max_ram_gb is not None:
            updates.append("max_ram_gb = ?")
            params.append(max_ram_gb)
        if max_disk_gb is not None:
            updates.append("max_disk_gb = ?")
            params.append(max_disk_gb)
        if updates:
            updates.append("updated_at = ?")
            params.append(int(time.time()))
            sql = f"UPDATE vps_inventory SET {', '.join(updates)} WHERE ip = ?"
            params.append(ip)
            return conn.execute(sql, params).rowcount > 0
        return False

def remove_vps(ip: str) -> bool:
    """Delete VPS from inventory."""
    with get_connection("system") as conn:
        cursor = conn.execute("DELETE FROM vps_inventory WHERE ip = ?", (ip,))
        return cursor.rowcount > 0

def list_vps(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """Return all configured VPS."""
    query = "SELECT * FROM vps_inventory"
    if enabled_only: query += " WHERE enabled = 1"
    query += " ORDER BY name ASC"
    with get_connection("system") as conn:
        cursor = conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get config value."""
    with get_connection("system") as conn:
        cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_config(key: str, value: str) -> None:
    """Upsert config value."""
    ts = int(time.time())
    with get_connection("system") as conn:
        conn.execute("INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?", (key, value, ts, value, ts))

def get_alert_state(vps_ip: str) -> Optional[Dict[str, Any]]:
    """Get current status/alert tracking for a VPS."""
    with get_connection("system") as conn:
        cursor = conn.execute("SELECT * FROM alert_state WHERE vps_ip = ?", (vps_ip,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_alert_state(vps_ip: str, status: str, alert_timestamp: Optional[int] = None, security_hash: Optional[str] = None) -> None:
    """Sync alert state for a VPS."""
    with get_connection("system") as conn:
        conn.execute("""
            INSERT INTO alert_state (vps_ip, last_status, last_alert_timestamp, last_security_hash) VALUES (?, ?, ?, ?)
            ON CONFLICT(vps_ip) DO UPDATE SET 
                last_status = ?, 
                last_alert_timestamp = COALESCE(?, last_alert_timestamp),
                last_security_hash = COALESCE(?, last_security_hash)
        """, (vps_ip, status, alert_timestamp, security_hash, status, alert_timestamp, security_hash))

# Auto-initialize on import
init_db()
