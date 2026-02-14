"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

Database maintenance utility. Detects and removes corrupt data or impossible outliers.
"""

import sqlite3
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
SYSTEM_DB = BASE_DIR / "aigents_pulse.db"
DOCKER_DB = BASE_DIR / "aigents_dockers_vps.db"

def deep_clean():
    """Aggressive cleaning of system and docker metrics to fix visualization scaling."""
    logger.info("Starting Deep Clean Protocol...")
    
    # 1. Clean System Metrics (status_history)
    if SYSTEM_DB.exists():
        try:
            with sqlite3.connect(str(SYSTEM_DB)) as conn:
                cursor = conn.cursor()
                
                # Delete CPU/RAM > 100% (impossible)
                cursor.execute("DELETE FROM status_history WHERE cpu_percent > 100 OR ram_percent > 100")
                deleted_metrics = cursor.rowcount
                
                # Delete Latency > 5000ms (absurd/timeout)
                cursor.execute("DELETE FROM status_history WHERE latency_ms > 5000")
                deleted_latency = cursor.rowcount
                
                conn.commit()
                logger.info(f"✓ System DB Cleaned: Removed {deleted_metrics} impossible metrics and {deleted_latency} high latency records.")
        except Exception as e:
            logger.error(f"Error cleaning System DB: {e}")
            
    # 2. Clean Docker Snapshots (docker_snapshots)
    if DOCKER_DB.exists():
        try:
            with sqlite3.connect(str(DOCKER_DB)) as conn:
                cursor = conn.cursor()
                
                # Remove rows with the specific known corrupt value (1.6TB)
                # The user specified 1,689,046 MB
                cursor.execute("DELETE FROM docker_snapshots WHERE containers_json LIKE '%1689046%'")
                specific_deleted = cursor.rowcount
                
                # General safety net for other massive outliers
                # RAM > 1TB (1048576 MB)
                cursor.execute("DELETE FROM docker_snapshots WHERE containers_json LIKE '%\"memory_mb\": 1_______.%'") # Regex-like wildcard for 7+ digits
                # NOTE: SQLite LIKE is limited, better to use the specific value or do Python-side filtering if needed. 
                # But the user provided script used LIKE '%1689046%', so we stick to that + strict Python iteration for safety.
                
                conn.commit()
                
                # Double check with Python iteration for anything missed by simple LIKE
                cursor.execute("SELECT id, containers_json FROM docker_snapshots")
                rows = cursor.fetchall()
                ids_to_delete = []
                
                for row_id, data in rows:
                    if not data: continue
                    try:
                        containers = json.loads(data)
                        for c in containers:
                            # 100GB limit for Docker container (conservative sanify check for a VPS)
                            if c.get('memory_mb', 0) > 102400: 
                                ids_to_delete.append(row_id)
                                break
                            # 500% CPU is technically possible on 5+ cores, but 98000% is not. 
                            # Let's cap at 6400% (64 cores) to be safe, or just check for "inf" / NaN
                            if c.get('cpu_percent', 0) > 10000:
                                ids_to_delete.append(row_id)
                                break
                    except:
                        ids_to_delete.append(row_id) # Delete corrupt JSON
                
                if ids_to_delete:
                    cursor.executemany("DELETE FROM docker_snapshots WHERE id = ?", [(i,) for i in ids_to_delete])
                    conn.commit()
                    logger.info(f"✓ Docker DB Deep Scanned: Removed {len(ids_to_delete)} additional corrupt snapshots.")
                
                logger.info(f"✓ Docker DB Cleaned: Removed {specific_deleted} rows matching known corrupt signature.")
                
                # Optimize
                conn.execute("VACUUM")

        except Exception as e:
            logger.error(f"Error cleaning Docker DB: {e}")

if __name__ == "__main__":
    deep_clean()
