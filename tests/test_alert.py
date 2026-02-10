import pytest
import alert
import db
import os
from unittest.mock import patch

def test_alert_logic():
    vps_ip = "10.0.0.1"
    vps_name = "Alert VPS"
    
    # Ensure clean slate
    db.remove_vps(vps_ip)
    db.add_vps(vps_ip, vps_name)
    
    # 1. State: UP (initial)
    alert.check_and_alert(vps_ip, vps_name, "UP")
    state = db.get_alert_state(vps_ip)
    assert state['last_status'] == "UP"
    assert state['last_alert_timestamp'] is None
    
    # 2. Transition: UP -> DOWN (Should Alert)
    with patch('notification.send_alert') as mock_send:
        alert.check_and_alert(vps_ip, vps_name, "DOWN")
        state = db.get_alert_state(vps_ip)
        assert state['last_status'] == "DOWN"
        assert state['last_alert_timestamp'] is not None
        mock_send.assert_called_once()
    
    # 3. State: DOWN (No new alert)
    with patch('notification.send_alert') as mock_send:
        alert.check_and_alert(vps_ip, vps_name, "DOWN")
        mock_send.assert_not_called()
    
    # 4. Transition: DOWN -> UP (Reset, No Alert)
    alert.check_and_alert(vps_ip, vps_name, "UP")
    state = db.get_alert_state(vps_ip)
    assert state['last_status'] == "UP"
    
    db.remove_vps(vps_ip)
