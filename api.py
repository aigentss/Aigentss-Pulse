"""
Aigents Pulse v3.1 (Spectre+)
Developed by: Ing. Ángel David Yaguana, Dr. h.c. - CAIO & CIO | Aigents Solutions
Date: 2026-02-10
Propietario: Aigents Solutions

REST API for Aigents Pulse. Provides endpoints for VPS inventory and metrics.
"""

from fastapi import FastAPI, HTTPException, Depends
from typing import List, Dict, Any, Optional
import db
import uvicorn

app = FastAPI(
    title="Aigents Pulse API",
    description="REST API for infrastructure monitoring and observability",
    version="3.1.0"
)

# Standard Signature Header
@app.middleware("http")
async def add_signature_header(request, call_next):
    response = await call_next(request)
    response.headers["X-Developed-By"] = "Ing. Ángel David Yaguana - Aigents Solutions"
    return response

@app.get("/")
async def root():
    return {
        "app": "Aigents Pulse API",
        "version": "3.1.0",
        "developer": "Ing. Ángel David Yaguana",
        "organization": "Aigents Solutions",
        "status": "Online"
    }

@app.get("/vps", response_model=List[Dict[str, Any]])
async def get_vps_list(enabled_only: bool = False):
    """Retrieve the list of configured VPS nodes."""
    try:
        return db.list_vps(enabled_only=enabled_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vps/{ip}/latest")
async def get_vps_latest_status(ip: str):
    """Get the most recent system metrics for a specific VPS."""
    status = db.get_latest_status(ip)
    if not status:
        raise HTTPException(status_code=404, detail="VPS metrics not found")
    return status

@app.get("/vps/{ip}/docker/latest")
async def get_vps_latest_docker(ip: str):
    """Get the most recent Docker container snapshot for a VPS."""
    snapshot = db.get_latest_docker_snapshot(ip)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Docker snapshot not found")
    return snapshot

@app.get("/metrics/history")
async def get_metrics_history(ip: Optional[str] = None, limit: int = 100):
    """Query historical system metrics."""
    return db.get_history(vps_ip=ip, limit=limit)

@app.get("/metrics/docker/history/{ip}")
async def get_docker_history(ip: str, limit: int = 50):
    """Query historical Docker performance for a VPS."""
    return db.get_docker_history(ip, limit=limit)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
