"""Windows printing utilities for Peterbot.

Provides silent PDF printing via SumatraPDF (preferred) or PowerShell fallback.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from logger import logger


# Default printer from environment
DEFAULT_PRINTER = os.getenv("PETERBOT_PRINTER", "")

# SumatraPDF paths to try
SUMATRA_PATHS = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expanduser(r"~\AppData\Local\SumatraPDF\SumatraPDF.exe"),
]


def get_sumatra_path() -> Optional[str]:
    """Find SumatraPDF installation path.

    Returns:
        Path to SumatraPDF.exe if found, None otherwise
    """
    for path in SUMATRA_PATHS:
        if Path(path).exists():
            return path
    return None


def get_windows_printers() -> list[str]:
    """Get list of available Windows printers.

    Returns:
        List of printer names
    """
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            printers = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            return printers
    except Exception as e:
        logger.warning(f"Failed to enumerate printers: {e}")
    return []


def print_pdf_windows(pdf_path: str, printer_name: Optional[str] = None) -> tuple[bool, str]:
    """Print PDF to Windows printer using SumatraPDF or fallback.

    Args:
        pdf_path: Path to PDF file to print
        printer_name: Target printer name (uses default if not specified)

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not Path(pdf_path).exists():
        return False, f"PDF not found: {pdf_path}"

    printer = printer_name or DEFAULT_PRINTER
    if not printer:
        return False, "No printer configured (set PETERBOT_PRINTER)"

    # Try SumatraPDF first (silent printing)
    sumatra = get_sumatra_path()
    if sumatra:
        try:
            result = subprocess.run(
                [sumatra, "-print-to", printer, "-silent", pdf_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info(f"Printed {pdf_path} to {printer} via SumatraPDF")
                return True, f"Printed to {printer}"
            else:
                logger.warning(f"SumatraPDF print failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("SumatraPDF print timed out")
        except Exception as e:
            logger.warning(f"SumatraPDF print error: {e}")

    # Fallback: PowerShell Start-Process with print verb
    # This opens the default PDF viewer and sends to printer
    try:
        # Use Start-Process with -Verb Print for PDF association
        ps_cmd = f'Start-Process -FilePath "{pdf_path}" -Verb Print -PassThru | Wait-Process -Timeout 30'
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=45
        )
        if result.returncode == 0:
            logger.info(f"Printed {pdf_path} via PowerShell")
            return True, f"Printed to default printer (PowerShell fallback)"
        else:
            return False, f"PowerShell print failed: {result.stderr[:100]}"
    except subprocess.TimeoutExpired:
        return False, "Print timed out"
    except Exception as e:
        return False, f"Print error: {e}"


async def print_pick_lists(
    amazon_pdf: Optional[str],
    ebay_pdf: Optional[str],
    printer_name: Optional[str] = None
) -> dict:
    """Print pick list PDFs to Windows printer.

    Args:
        amazon_pdf: Path to Amazon pick list PDF (or None)
        ebay_pdf: Path to eBay pick list PDF (or None)
        printer_name: Target printer (uses default if not specified)

    Returns:
        Dict with print results for each platform:
        {
            "amazon": {"success": bool, "message": str} or None,
            "ebay": {"success": bool, "message": str} or None
        }
    """
    import asyncio

    results = {"amazon": None, "ebay": None}

    # Print Amazon PDF
    if amazon_pdf and Path(amazon_pdf).exists():
        success, message = await asyncio.to_thread(
            print_pdf_windows, amazon_pdf, printer_name
        )
        results["amazon"] = {"success": success, "message": message}
        logger.info(f"Amazon pick list print: {success} - {message}")
    elif amazon_pdf:
        results["amazon"] = {"success": False, "message": "PDF not found"}

    # Print eBay PDF
    if ebay_pdf and Path(ebay_pdf).exists():
        success, message = await asyncio.to_thread(
            print_pdf_windows, ebay_pdf, printer_name
        )
        results["ebay"] = {"success": success, "message": message}
        logger.info(f"eBay pick list print: {success} - {message}")
    elif ebay_pdf:
        results["ebay"] = {"success": False, "message": "PDF not found"}

    return results


def check_printer_ready(printer_name: Optional[str] = None) -> tuple[bool, str]:
    """Check if printer is available and ready.

    Args:
        printer_name: Printer to check (uses default if not specified)

    Returns:
        Tuple of (ready: bool, message: str)
    """
    printer = printer_name or DEFAULT_PRINTER
    if not printer:
        return False, "No printer configured"

    available = get_windows_printers()
    if printer in available:
        return True, f"Printer '{printer}' is available"
    elif available:
        return False, f"Printer '{printer}' not found. Available: {', '.join(available[:3])}"
    else:
        return False, "Could not enumerate printers"
