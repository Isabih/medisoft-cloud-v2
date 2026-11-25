"""Run on the cloud host only; no database writes or service changes."""
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

TARGET = Path(os.environ.get("CLOUD_STATUS_FILE", "/opt/monitoring/cloud_status.json"))

def service(name):
    try:
        result = subprocess.run(["systemctl", "is-active", name], capture_output=True,
                                text=True, timeout=5)
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"

def collect():
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    return {
        "hostname": os.uname().nodename,
        "cpu_usage": psutil.cpu_percent(interval=1),
        "cpu_cores": psutil.cpu_count(),
        "ram_usage": memory.percent,
        "ram_total_gb": round(memory.total / 1024**3, 2),
        "ram_free_gb": round(memory.available / 1024**3, 2),
        "disk_usage": round(disk.used / disk.total * 100, 2),
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "load_average": list(os.getloadavg()),
        "server_status": "online",
        "mysql_service_status": service("mysql.service"),
        "nginx_service_status": service("nginx.service"),
        "vpn_service_status": service("tailscaled.service"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

def write(data):
    fd, name = tempfile.mkstemp(prefix=".cloud-status-", dir=TARGET.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, 0o640)
        os.replace(name, TARGET)
    finally:
        if os.path.exists(name):
            os.unlink(name)

if __name__ == "__main__":
    while True:
        write(collect())
        time.sleep(15)
