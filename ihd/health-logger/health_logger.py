#!/usr/bin/env python3
"""
IHD Dashboard Health Logger
Checks all dashboard dependencies every 60s.
Only logs on state changes (healthy<->unhealthy) + hourly summary.
Log: ~/.data/ihd-health.log
"""

import time
import socket
import logging
import urllib.request
import urllib.error
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path.home() / ".data" / "ihd-health.log"
CHECK_INTERVAL = 60  # seconds
SUMMARY_INTERVAL = 3600  # hourly summary

# Dependencies to check
CHECKS = {
    "dns": {
        "type": "dns",
        "host": "google.com",
        "desc": "DNS resolution",
    },
    "mosquitto": {
        "type": "tcp",
        "host": "localhost",
        "port": 1883,
        "desc": "MQTT broker",
    },
    "zigbee_api": {
        "type": "tcp",
        "host": "localhost",
        "port": 5001,
        "desc": "Zigbee sensor API",
    },
    "zigbee2mqtt": {
        "type": "http",
        "url": "http://localhost:8080",
        "desc": "Zigbee2MQTT frontend",
    },
    "ihd_app": {
        "type": "http",
        "url": "http://localhost:3000",
        "desc": "IHD Next.js app",
    },
    "hadley_api": {
        "type": "tcp",
        "host": "192.168.0.87",
        "port": 8100,
        "desc": "Hadley API (Windows)",
    },
    "supabase": {
        "type": "http",
        "url": "https://modjoikyuhqzouxvieua.supabase.co/rest/v1/",
        "desc": "Supabase REST",
    },
    "weather": {
        "type": "dns",
        "host": "api.open-meteo.com",
        "desc": "Weather API DNS",
    },
}


def setup_logging():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ihd-health")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger


def check_dns(host):
    try:
        socket.getaddrinfo(host, 80, socket.AF_INET, socket.SOCK_STREAM)
        return True, None
    except socket.gaierror as e:
        return False, str(e)


def check_tcp(host, port):
    try:
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        return True, None
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return False, str(e)


def check_http(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=5)
        resp.close()
        return True, None
    except urllib.error.HTTPError as e:
        # 401/403 means the server is reachable (just auth-gated)
        if e.code in (401, 403):
            return True, None
        return False, f"HTTP {e.code}"
    except Exception as e:
        # Some endpoints don't support HEAD, try GET
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5)
            resp.read(100)
            resp.close()
            return True, None
        except urllib.error.HTTPError as e2:
            if e2.code in (401, 403):
                return True, None
            return False, f"HTTP {e2.code}"
        except Exception as e2:
            return False, str(e2)


def run_check(check):
    if check["type"] == "dns":
        return check_dns(check["host"])
    elif check["type"] == "tcp":
        return check_tcp(check["host"], check["port"])
    elif check["type"] == "http":
        return check_http(check["url"])
    return False, "unknown check type"


def main():
    log = setup_logging()
    log.info("=== IHD Health Logger started ===")

    # Track previous state per check
    prev_state = {}
    last_summary = time.time()

    while True:
        results = {}
        for name, check in CHECKS.items():
            ok, err = run_check(check)
            results[name] = (ok, err)

            prev_ok = prev_state.get(name)

            # Log on state change
            if prev_ok is None:
                # First run — log initial state
                if ok:
                    log.info(f"[OK]   {check['desc']} ({name})")
                else:
                    log.info(f"[FAIL] {check['desc']} ({name}): {err}")
            elif prev_ok and not ok:
                log.info(f"[DOWN] {check['desc']} ({name}): {err}")
            elif not prev_ok and ok:
                log.info(f"[RECOVERED] {check['desc']} ({name})")

            prev_state[name] = ok

        # Hourly summary
        now = time.time()
        if now - last_summary >= SUMMARY_INTERVAL:
            healthy = sum(1 for ok, _ in results.values() if ok)
            total = len(results)
            failed = [name for name, (ok, _) in results.items() if not ok]
            if failed:
                log.info(f"[SUMMARY] {healthy}/{total} healthy. Down: {', '.join(failed)}")
            else:
                log.info(f"[SUMMARY] {healthy}/{total} all healthy")
            last_summary = now

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
