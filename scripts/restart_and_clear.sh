#!/bin/bash
# Script to restart the monitoring daemon and clear cache
# This forces fresh recalculation of all metrics

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
