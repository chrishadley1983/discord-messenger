"""
Browser API Routes

Endpoints for browser automation control.
These endpoints are protected and require API key authentication.
"""

import sys
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_agent import BrowserService, SpendingLimiter
from browser_agent.domain_allowlist import ALLOWED_DOMAINS

router = APIRouter(prefix="/browser", tags=["browser"])

# Service instances
_browser_service: Optional[BrowserService] = None
_spending_limiter: Optional[SpendingLimiter] = None


def get_browser_service() -> BrowserService:
    """Get or create browser service instance."""
    global _browser_service
    if _browser_service is None:
        _browser_service = BrowserService()
    return _browser_service


def get_spending_limiter() -> SpendingLimiter:
    """Get or create spending limiter instance."""
    global _spending_limiter
    if _spending_limiter is None:
        _spending_limiter = SpendingLimiter()
    return _spending_limiter


# Request/Response models


class SessionStartRequest(BaseModel):
    """Request to start a browser session."""

    domain: str = Field(..., description="Target domain (e.g., 'amazon.co.uk')")
    user_id: int = Field(..., description="Discord user ID")
    channel_id: int = Field(..., description="Discord channel ID")


class SessionStartResponse(BaseModel):
    """Response from starting a browser session."""

    session_id: str
    domain: str
    authenticated: bool
    viewport: dict
    url: str
    title: str
    message: str


class SessionEndRequest(BaseModel):
    """Request to end a browser session."""

    session_id: str = Field(..., description="Session ID to close")
    save_state: bool = Field(True, description="Whether to save session cookies")


class SessionEndResponse(BaseModel):
    """Response from ending a browser session."""

    success: bool
    session_id: str
    duration_seconds: float
    action_count: int
    message: str


class ActionRequest(BaseModel):
    """Request to execute a browser action."""

    session_id: str = Field(..., description="Active session ID")
    action: Literal["navigate", "click", "click_text", "click_role", "type", "press", "scroll", "wait"] = Field(
        ..., description="Action type"
    )
    params: dict = Field(default_factory=dict, description="Action parameters")
    purchase_id: Optional[str] = Field(None, description="Optional purchase ID for audit")


class ActionResponse(BaseModel):
    """Response from executing a browser action."""

    success: bool
    action_type: str
    message: str
    url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class ScreenshotResponse(BaseModel):
    """Response containing a screenshot."""

    success: bool
    screenshot: Optional[str] = None  # base64 encoded PNG
    url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None


class LimitsResponse(BaseModel):
    """Response containing spending limits and usage."""

    limits: dict
    usage: dict
    remaining: dict


class CheckPurchaseRequest(BaseModel):
    """Request to check if a purchase is allowed."""

    amount: float = Field(..., description="Purchase amount in GBP")
    user_id: Optional[int] = Field(None, description="Optional user ID to check")


class CheckPurchaseResponse(BaseModel):
    """Response from purchase check."""

    allowed: bool
    reason: str
    limits: dict
    usage: dict
    remaining: dict


class DomainsResponse(BaseModel):
    """Response listing allowed domains."""

    domains: list[dict]


# Endpoints


@router.get("/domains", response_model=DomainsResponse)
async def list_allowed_domains():
    """
    List all allowed domains for browser automation.

    Returns the domain allowlist with configuration details.
    """
    domains = [
        {
            "domain": domain,
            "display_name": config.display_name,
            "max_order_gbp": config.max_order_gbp,
        }
        for domain, config in ALLOWED_DOMAINS.items()
    ]
    return DomainsResponse(domains=domains)


@router.get("/limits", response_model=LimitsResponse)
async def get_spending_limits(
    user_id: Optional[int] = Query(None, description="Optional user ID"),
    limiter: SpendingLimiter = Depends(get_spending_limiter),
):
    """
    Get current spending limits and usage.

    Returns configured limits and how much has been spent today/this week.
    """
    status = await limiter.get_status(user_id)
    return LimitsResponse(**status.to_dict())


@router.post("/limits/check", response_model=CheckPurchaseResponse)
async def check_purchase_allowed(
    request: CheckPurchaseRequest,
    limiter: SpendingLimiter = Depends(get_spending_limiter),
):
    """
    Check if a purchase amount is within spending limits.

    Use this before proceeding with a purchase to verify it won't exceed limits.
    """
    allowed, reason, status = await limiter.check_purchase(request.amount, request.user_id)
    return CheckPurchaseResponse(
        allowed=allowed,
        reason=reason,
        **status.to_dict(),
    )


@router.post("/session/start", response_model=SessionStartResponse)
async def start_browser_session(
    request: SessionStartRequest,
    service: BrowserService = Depends(get_browser_service),
):
    """
    Start a new browser session for an allowed domain.

    The session will use stored authentication if available.
    Only one session can be active at a time.
    """
    try:
        info, message = await service.start_session(
            domain=request.domain,
            user_id=request.user_id,
            channel_id=request.channel_id,
        )
        return SessionStartResponse(
            session_id=info.session_id,
            domain=info.domain,
            authenticated=info.authenticated,
            viewport=info.viewport,
            url=info.url,
            title=info.title,
            message=message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_info(
    session_id: str,
    service: BrowserService = Depends(get_browser_service),
):
    """
    Get information about an active session.
    """
    info = await service.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "session_id": info.session_id,
        "domain": info.domain,
        "authenticated": info.authenticated,
        "viewport": info.viewport,
        "url": info.url,
        "title": info.title,
        "duration_seconds": info.duration_seconds,
        "action_count": info.action_count,
    }


@router.post("/session/end", response_model=SessionEndResponse)
async def end_browser_session(
    request: SessionEndRequest,
    service: BrowserService = Depends(get_browser_service),
):
    """
    End a browser session.

    Optionally saves session state (cookies) for future use.
    """
    success, stats = await service.end_session(
        session_id=request.session_id,
        save_state=request.save_state,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=stats.get("error", "Session not found"),
        )

    return SessionEndResponse(
        success=True,
        session_id=request.session_id,
        duration_seconds=stats.get("duration_seconds", 0),
        action_count=stats.get("action_count", 0),
        message="Session closed successfully",
    )


@router.get("/screenshot", response_model=ScreenshotResponse)
async def get_screenshot(
    session_id: str = Query(..., description="Active session ID"),
    full_page: bool = Query(False, description="Capture full page"),
    service: BrowserService = Depends(get_browser_service),
):
    """
    Take a screenshot of the current page.

    Returns base64-encoded PNG image.
    """
    result = await service.screenshot(session_id, full_page)

    if not result.success:
        raise HTTPException(
            status_code=404 if "not found" in result.message.lower() else 500,
            detail=result.error or result.message,
        )

    return ScreenshotResponse(
        success=True,
        screenshot=result.screenshot,
        url=result.url,
        title=result.title,
    )


@router.post("/action", response_model=ActionResponse)
async def execute_action(
    request: ActionRequest,
    service: BrowserService = Depends(get_browser_service),
):
    """
    Execute a browser action.

    Supported actions:
    - navigate: {"url": "https://..."}
    - click: {"x": 100, "y": 200}
    - click_text: {"text": "Add to Basket", "exact": false}
    - click_role: {"role": "button", "name": "Add to Basket"}
    - type: {"text": "search query", "delay_ms": 50}
    - press: {"key": "Enter"}
    - scroll: {"direction": "down", "amount": 500}
    - wait: {"ms": 1000}
    """
    result = await service.execute_action(
        session_id=request.session_id,
        action=request.action,
        params=request.params,
        purchase_id=request.purchase_id,
    )

    if not result.success:
        # Check for security violations - these should be 403
        if result.error and "Security" in result.error:
            raise HTTPException(status_code=403, detail=result.error)

        # Session not found
        if "not found" in result.message.lower():
            raise HTTPException(status_code=404, detail=result.message)

        # Other errors
        raise HTTPException(status_code=400, detail=result.error or result.message)

    return ActionResponse(
        success=True,
        action_type=result.action_type,
        message=result.message,
        url=result.url,
        title=result.title,
        duration_ms=result.duration_ms,
    )


@router.get("/text")
async def get_page_text(
    session_id: str = Query(..., description="Active session ID"),
    service: BrowserService = Depends(get_browser_service),
):
    """
    Get visible text content from the current page.

    Useful for understanding page state without screenshots.
    """
    result = await service.get_page_text(session_id)

    if not result.success:
        raise HTTPException(
            status_code=404 if "not found" in result.message.lower() else 500,
            detail=result.error or result.message,
        )

    return {
        "success": True,
        "text": result.message,
        "url": result.url,
        "title": result.title,
    }


@router.get("/fetch")
async def fetch_page_with_browser(
    url: str = Query(..., description="URL to fetch"),
    wait_ms: int = Query(3000, description="Wait time after page load (ms)"),
):
    """
    Fetch a page using a real browser (bypasses bot protection).

    This is a convenience endpoint that:
    1. Launches a headless browser
    2. Navigates to the URL
    3. Waits for content to load
    4. Extracts visible text
    5. Closes the browser

    Use this for sites that block normal HTTP requests (e.g., Cloudflare, bot detection).
    Any URL is allowed (read-only, no purchases possible).
    """
    from urllib.parse import urlparse

    # Validate URL
    parsed = urlparse(url)
    if not parsed.hostname or parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL - must be http or https")

    try:
        # Use direct Playwright - no allowlist needed for read-only browsing
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            # Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for dynamic content
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)

            # Get page info
            title = await page.title()
            final_url = page.url

            # Extract visible text
            text = await page.evaluate("""
                () => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: (node) => {
                                const style = window.getComputedStyle(node.parentElement);
                                if (style.display === 'none' || style.visibility === 'hidden') {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    const texts = [];
                    while (walker.nextNode()) {
                        const text = walker.currentNode.textContent.trim();
                        if (text) texts.push(text);
                    }
                    return texts.join('\\n');
                }
            """)

            await browser.close()

            return {
                "success": True,
                "url": final_url,
                "title": title,
                "text": text,
                "domain": parsed.hostname,
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Browser fetch failed: {str(e)}")
