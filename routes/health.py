from fastapi import APIRouter
import time

router = APIRouter()

start_time = time.time()

@router.get("/health")
def health():
    uptime = round(time.time() - start_time, 2)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "version": "2026.1"
    }
