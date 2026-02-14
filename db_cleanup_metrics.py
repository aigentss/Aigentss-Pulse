
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

def clean_system_metrics():
    """Remove impossible system metrics (CPU > 110%, RAM > 100%)."""
    if not SYSTEM_DB.exists():
        logger.warning(f"System DB not found at {SYSTEM_DB}")
        return

    try:
        conn = sqlite3.connect(str(SYSTEM_DB))
        cursor = conn.cursor()
        
        # 1. Flag bad data
        cursor.execute("SELECT COUNT(*) FROM status_history WHERE cpu_percent > 110 OR ram_percent > 100")
        bad_count = cursor.fetchone()[0]
        
        if bad_count > 0:
            logger.info(f"Found {bad_count} corrupt system metric records. Deleting...")
            cursor.execute("DELETE FROM status_history WHERE cpu_percent > 110 OR ram_percent > 100")
            conn.commit()
            logger.info("Content deleted.")
        else:
            logger.info("System metrics look clean.")
            
        conn.close()
    except Exception as e:
        logger.error(f"Error cleaning system DB: {e}")

def clean_docker_snapshots():
    """Scan Docker snapshots and delete rows with impossible values."""
    if not DOCKER_DB.exists():
        logger.warning(f"Docker DB not found at {DOCKER_DB}")
        return

    try:
        conn = sqlite3.connect(str(DOCKER_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        logger.info("Scanning Docker snapshots for corruption (Memory > 1TB or CPU > 500%)...")
        
        cursor.execute("SELECT id, containers_json FROM docker_snapshots")
        rows = cursor.fetchall()
        
        delete_ids = []
        
        for row in rows:
            try:
                containers = json.loads(row['containers_json'])
                is_corrupt = False
                
                for c in containers:
                    # Check Memory: > 1,000,000 MB (1TB) -> Corrupt (likely timestamp bug)
                    mem_mb = c.get('memory_mb', 0)
                    if mem_mb > 1000000:
                        is_corrupt = True
                        break
                    
                    # Check CPU: > 500% -> Likely corrupt (timestamp bug caused 98000%)
                    cpu_pct = c.get('cpu_percent', 0)
                    if cpu_pct > 500:
                        is_corrupt = True
                        break
                
                if is_corrupt:
                    delete_ids.append(row['id'])
                    
            except json.JSONDecodeError:
                logger.warning(f"Found invalid JSON in row {row['id']}. Marking for deletion.")
                delete_ids.append(row['id'])
        
        if delete_ids:
            logger.info(f"Found {len(delete_ids)} corrupt snapshot rows out of {len(rows)}. Deleting...")
            # Batch delete
            placeholders = ','.join('?' * len(delete_ids))
            sql = f"DELETE FROM docker_snapshots WHERE id IN ({placeholders})"
            cursor.execute(sql, delete_ids)
            conn.commit()
            logger.info("Corrupt snapshots deleted.")
            
            # VACUUM to reclaim space
            logger.info("Vacuuming database...")
            conn.execute("VACUUM")
        else:
            logger.info("Docker snapshots look clean.")
            
        conn.close()
    except Exception as e:
        logger.error(f"Error cleaning Docker DB: {e}")

if __name__ == "__main__":
    print("--- Starting Database Cleanup ---")
    clean_system_metrics()
    clean_docker_snapshots()
    print("--- Cleanup Complete ---")
