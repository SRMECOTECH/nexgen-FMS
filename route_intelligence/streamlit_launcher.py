"""
Background Streamlit supervisor.

When FastAPI boots, ``ensure_started()`` spawns ``streamlit run streamlit_app/app.py``
unless the port is already serving. The subprocess is detached (its own process
group) so it survives Uvicorn's auto-reload; on a clean shutdown the launcher
sends a terminate signal.

All knobs come from ``config/route_intel.yaml`` (``streamlit.*``). If Streamlit
isn't installed, we log and stay silent — the FastAPI/React part still works.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from route_intelligence import config as ricfg

logger = logging.getLogger(__name__)

_PROC: Optional[subprocess.Popen] = None
_LOCK = threading.Lock()


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def is_healthy() -> bool:
    host = ricfg.get("streamlit", "host", "127.0.0.1")
    port = ricfg.streamlit_port()
    if not _port_open(host, port):
        return False
    try:
        r = requests.get(f"http://{host}:{port}/_stcore/health", timeout=1.5)
        return r.status_code == 200 and r.text.strip().lower() == "ok"
    except Exception:
        return False


def status() -> dict:
    return {
        "configured_url": ricfg.streamlit_url(),
        "running": is_healthy(),
        "managed_pid": _PROC.pid if _PROC and _PROC.poll() is None else None,
        "autostart": bool(ricfg.get("streamlit", "autostart", True)),
        "app_file": str(ricfg.streamlit_app_file()),
    }


def ensure_started() -> dict:
    """Idempotent: launch Streamlit unless something is already serving on the
    configured port. Returns the same dict as :func:`status`."""
    global _PROC
    if not ricfg.get("streamlit", "autostart", True):
        logger.info("streamlit_launcher: autostart disabled")
        return status()

    with _LOCK:
        if is_healthy():
            logger.info("streamlit_launcher: already healthy at %s", ricfg.streamlit_url())
            return status()

        app_file = ricfg.streamlit_app_file()
        if not app_file.exists():
            logger.warning("streamlit_launcher: app file missing → %s", app_file)
            return status()

        try:
            import streamlit  # noqa: F401  — ensure it's importable
        except Exception as exc:
            logger.warning("streamlit_launcher: streamlit not installed (%s)", exc)
            return status()

        host = ricfg.get("streamlit", "host", "127.0.0.1")
        port = ricfg.streamlit_port()
        headless = bool(ricfg.get("streamlit", "headless", True))
        grace = float(ricfg.get("streamlit", "startup_grace_sec", 2.0))

        cmd = [
            sys.executable, "-m", "streamlit", "run", str(app_file),
            f"--server.address={host}",
            f"--server.port={port}",
            f"--server.headless={'true' if headless else 'false'}",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        logger.info("streamlit_launcher: spawning → %s", " ".join(cmd))

        # Detach: on Windows use CREATE_NEW_PROCESS_GROUP; elsewhere setsid.
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True

        try:
            _PROC = subprocess.Popen(
                cmd,
                cwd=str(ricfg.project_root()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
        except Exception as exc:
            logger.exception("streamlit_launcher: spawn failed: %s", exc)
            return status()

        # Give the process a moment to bind the port so the UI's first probe
        # doesn't see "not running" right after FastAPI comes up.
        for _ in range(int(grace * 5)):
            if _port_open(host, port):
                break
            time.sleep(0.2)
        return status()


def stop() -> None:
    global _PROC
    with _LOCK:
        if _PROC and _PROC.poll() is None:
            try:
                _PROC.terminate()
            except Exception:
                pass
        _PROC = None
