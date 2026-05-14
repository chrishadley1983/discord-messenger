"""Chrome launcher + CDP connection helpers for the Prolific monitor.

Why subprocess.Popen (not Playwright launch_persistent_context):
- Chrome 136+ silently ignores --remote-debugging-port when using the default
  user-data-dir. Must point at a dedicated profile (Chrome-Prolific).
- Playwright's launched Chromium adds --enable-automation, which Prolific
  may flag. Launching real Chrome ourselves keeps a clean fingerprint, then
  we attach via connect_over_cdp.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from contextlib import asynccontextmanager

import httpx

from logger import logger

from .config import CDP_PORT, CHROME_EXE, PROFILE_DIR


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _chrome_alive() -> bool:
    """True if Chrome is listening on CDP_PORT and responding to /json/version."""
    if not _is_port_open(CDP_PORT):
        return False
    try:
        r = httpx.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def ensure_chrome_running(headless: bool = True) -> None:
    """Spawn Chrome-Prolific if not already running. Idempotent."""
    if _chrome_alive():
        return

    if not CHROME_EXE.exists():
        raise RuntimeError(f"Chrome not found at {CHROME_EXE}")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        str(CHROME_EXE),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=ChromeWhatsNewUI",
    ]
    if headless:
        args.append("--headless=new")
        args.append("--window-size=1280,900")

    logger.info(f"Launching Chrome-Prolific on CDP port {CDP_PORT} (headless={headless})")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        if _chrome_alive():
            logger.info("Chrome-Prolific is up")
            return
        time.sleep(0.5)
    raise RuntimeError(f"Chrome-Prolific failed to open CDP port {CDP_PORT} within 15s")


@asynccontextmanager
async def cdp_page(headless: bool = True):
    """Yield a Playwright Page connected to the running Chrome-Prolific.

    Reuses an existing page if one is open; otherwise creates a new one in the
    first available context. Closes the new page on exit (leaves Chrome up).
    """
    await asyncio.to_thread(ensure_chrome_running, headless)

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        contexts = browser.contexts
        if not contexts:
            ctx = await browser.new_context()
            close_ctx = True
        else:
            ctx = contexts[0]
            close_ctx = False

        page = await ctx.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                pass
            if close_ctx:
                try:
                    await ctx.close()
                except Exception:
                    pass
            try:
                await browser.close()
            except Exception:
                pass
