import pytest
import os
import sqlite3
import db
import time

def test_db_init():
    # Should be initialized on import, but we can verify tables
    tables = []
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]
    
    assert 'status_history' in tables
    assert 'vps_inventory' in tables
    assert 'docker_snapshots' in tables
    assert 'config' in tables
    assert 'alert_state' in tables

def test_vps_crud():
    ip = "1.2.3.4"
    name = "Test VPS"
    
    # Add
    assert db.add_vps(ip, name) is True
    assert db.add_vps(ip, name) is False  # Duplicate
    
    # List
    vps_list = db.list_vps()
    assert any(v['ip'] == ip for v in vps_list)
    
    # Update
    assert db.update_vps(ip, name="Updated VPS", enabled=False) is True
    
    # Remove
    assert db.remove_vps(ip) is True
    assert db.remove_vps(ip) is False

def test_status_history():
    ip = "5.6.7.8"
    name = "History VPS"
    
    db.add_vps(ip, name)
    
    # Save status
    assert db.save_status(ip, name, "UP", 10.5, 20.0, 30.0, 40.0) is True
    
    # Get history
    history = db.get_last_24h(ip)
    assert len(history) >= 1
    assert history[0]['status'] == "UP"
    assert history[0]['latency_ms'] == 10.5
    
    db.remove_vps(ip)
