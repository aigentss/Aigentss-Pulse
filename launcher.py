#!/usr/bin/env python3
"""
Aigentss Pulse Launcher - Keep-Alive System [EVOLUTION]
Monitors and auto-restarts app.py and monitor.py if they crash.
Enhanced with SIGKILL for zombie processes and async logging.
"""

import subprocess
import time
import logging
import os
import signal
import sys
import psutil

# Configuration
CHECK_INTERVAL = 60  # seconds
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(APP_DIR, "logs")
LAUNCHER_LOG = os.path.join(LOG_DIR, "launcher.log")
MONITOR_LOG = os.path.join(LOG_DIR, "monitor.log")
STREAMLIT_LOG = os.path.join(LOG_DIR, "streamlit.log")

# Create logs directory
os.makedirs(LOG_DIR, exist_ok=True)

# Logging setup (Async-friendly: simple file writes)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LAUNCHER_LOG),
        logging.StreamHandler()
    ]
)

# Process tracking
processes = {
    "monitor": None,
    "streamlit": None
}

def kill_existing_processes():
    """Robust killing of existing monitor.py or app.py processes using SIGKILL fallback."""
    killed_any = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'monitor.py' in cmdline or ('streamlit' in cmdline and 'app.py' in cmdline):
                # Don't kill ourselves
                if proc.info['pid'] == os.getpid():
                    continue
                
                logging.info(f"Terminating process: PID {proc.info['pid']} - {cmdline[:60]}...")
                proc.terminate() # SIGTERM first
                
                # Wait for death or kill -9
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    logging.warning(f"Process {proc.info['pid']} unresponsive. Sending SIGKILL (-9)...")
                    proc.kill() # SIGKILL
                
                killed_any = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_any:
        time.sleep(2)
        logging.info("Clean slate: All existing processes purged.")

def is_process_running(proc):
    if proc is None:
        return False
    return proc.poll() is None

def start_monitor():
    try:
        logging.info("Starting monitor.py [Bypass Mode: 9100]...")
        # redirection to log file async via Popen
        log_f = open(MONITOR_LOG, 'a')
        proc = subprocess.Popen(
            ["python3", "monitor.py"],
            cwd=APP_DIR,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            bufsize=1 # Line buffered for faster log updates
        )
        logging.info(f"monitor.py running with PID {proc.pid}")
        return proc
    except Exception as e:
        logging.error(f"Failed to start monitor: {e}")
        return None

def start_streamlit():
    try:
        logging.info("Starting Streamlit app.py [Evolution UI]...")
        log_f = open(STREAMLIT_LOG, 'a')
        proc = subprocess.Popen(
            ["streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true"],
            cwd=APP_DIR,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            bufsize=1
        )
        logging.info(f"Streamlit running with PID {proc.pid}")
        return proc
    except Exception as e:
        logging.error(f"Failed to start app: {e}")
        return None

def stop_all_processes():
    logging.info("Shutting down infrastructure...")
    for name, proc in processes.items():
        if proc and is_process_running(proc):
            try:
                logging.info(f"Stopping {name} (PID {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    logging.info(f"{name} exited.")
                except subprocess.TimeoutExpired:
                    logging.warning(f"{name} took too long. Force killing.")
                    proc.kill()
            except Exception as e:
                logging.error(f"Shutdown error for {name}: {e}")

def signal_handler(signum, frame):
    logging.info(f"Signal {signum} caught.")
    stop_all_processes()
    sys.exit(0)

def main():
    logging.info("=== Aigentss Pulse Infinity Core Launcher Started ===")
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    kill_existing_processes()
    
    processes["monitor"] = start_monitor()
    logging.info("Waiting 5s for Core stabilization...")
    time.sleep(5)
    processes["streamlit"] = start_streamlit()
    
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            
            if not is_process_running(processes["monitor"]):
                logging.warning("Monitor failure detected! Resuscitating...")
                processes["monitor"] = start_monitor()
            
            if not is_process_running(processes["streamlit"]):
                logging.warning("UI failure detected! Resuscitating...")
                processes["streamlit"] = start_streamlit()
                
    except KeyboardInterrupt:
        stop_all_processes()
    except Exception as e:
        logging.error(f"Launcher crash: {e}")
        stop_all_processes()
        raise

if __name__ == "__main__":
    main()
