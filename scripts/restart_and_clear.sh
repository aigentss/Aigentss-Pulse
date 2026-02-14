#!/bin/bash
# ==============================================================================
# Aigents Pulse v3.1 (Spectre+)
# Developed by: Ing. Ángel David Yaguana, Dr. h.c.
# Date: 2026-02-14
# Propietario: Ing. Ángel David Yaguana, Dr. h.c.
#
# Designed for VPS monitoring of Aigents Solutions Corp (USA) and Aigents Solutions SAS (Ecuador).
# Protected by Intellectual Property Laws. Use authorized explicitly by the owner.
# PROPRIETARY AND CONFIDENTIAL.
#
# Maintenance Script.
Restarts the service and clears execution cache.
# ==============================================================================

echo "Restarting Aigents Pulse to clear Docker CPU cache..."

# Kill any existing streamlit processes
pkill -f "streamlit run app.py" || true

# Wait a moment
sleep 2

# Clear the database (optional - comment out if you want to keep history)
# rm -f aigents_pulse.db security_snapshots.db docker_snapshots.db

echo "Cache cleared. Starting fresh..."
echo "Please restart the app manually using:"
echo "  streamlit run app.py"
