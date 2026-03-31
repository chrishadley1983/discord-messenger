"""UI tests for the Goals dashboard view.

Tests the GoalsView JavaScript component logic by verifying
the HTML output and API proxy endpoint accessibility.
Requires the Peter Dashboard running on localhost:5000.
"""

import os
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_URL = "http://localhost:5000"
API_PROXY = f"{DASHBOARD_URL}/api/hadley/proxy"
API_KEY = os.getenv("HADLEY_AUTH_KEY", "")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=15, headers={"x-api-key": API_KEY}) as c:
        yield c


# ── Dashboard Availability ───────────────────────────────────────────────

class TestDashboardAvailability:
    """Verify the dashboard is running and the goals page is accessible."""

    def test_dashboard_reachable(self, client):
        resp = client.get(DASHBOARD_URL)
        assert resp.status_code == 200

    def test_dashboard_html_has_goals_nav(self, client):
        resp = client.get(DASHBOARD_URL)
        html = resp.text
        assert 'href="#/goals"' in html, "Goals nav link not found in sidebar"
        assert 'title="Goals"' in html, "Goals nav title not found"

    def test_dashboard_html_has_goals_icon(self, client):
        resp = client.get(DASHBOARD_URL)
        html = resp.text
        assert 'data-route="/goals"' in html, "Goals route not found in sidebar"

    def test_app_js_has_goals_view(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        assert resp.status_code == 200
        js = resp.text
        assert "GoalsView" in js, "GoalsView not found in app.js"
        assert "goals-grid" in js, "goals-grid class not found in app.js"
        assert "goal-card" in js, "goal-card class not found in app.js"
        assert "showAddModal" in js, "showAddModal function not found"
        assert "showLogModal" in js, "showLogModal function not found"
        assert "logProgress" in js, "logProgress function not found"

    def test_css_has_goal_styles(self, client):
        # Try with version param matching the HTML
        resp = client.get(f"{DASHBOARD_URL}/static/css/main.css")
        assert resp.status_code == 200
        css = resp.text
        assert ".goal-card" in css, "goal-card styles not found in CSS"
        assert ".goal-progress-bar" in css, "progress bar styles not found"
        assert ".goal-progress-fill" in css, "progress fill styles not found"
        assert ".goals-grid" in css, "goals-grid styles not found"
        assert ".heatmap-cell" in css, "heatmap styles not found"
        assert ".heatmap-hit" in css, "heatmap-hit styles not found"


# ── API Proxy ────────────────────────────────────────────────────────────

class TestAPIProxy:
    """Verify the dashboard proxy forwards requests to Hadley API.

    Note: The dashboard proxy does not forward x-api-key headers.
    The GoalsView JS code uses the dashboard's own API client which
    injects the key from the meta tag. These tests verify the proxy
    route exists and forwards correctly when auth is handled.
    """

    def test_proxy_route_exists(self, client):
        """Proxy endpoint responds (even if 401 — route exists)."""
        resp = client.get(f"{API_PROXY}/accountability/goals")
        # 200 (no auth needed) or 401 (auth needed but not forwarded) — both prove route exists
        assert resp.status_code in (200, 401)

    def test_proxy_forwards_to_hadley(self, client):
        """Proxy returns a JSON response from Hadley API (not a 404/503)."""
        resp = client.get(f"{API_PROXY}/accountability/goals")
        # If 401, it means Hadley API received the request and rejected auth
        # If 200, it means Hadley API served the data
        # If 503, it means Hadley API is unreachable
        assert resp.status_code != 503, "Hadley API not reachable via proxy"

    def test_direct_api_goals_endpoint(self):
        """Verify goals endpoint works via direct Hadley API call."""
        with httpx.Client(timeout=10, headers={"x-api-key": API_KEY}) as c:
            resp = c.get("http://localhost:8100/accountability/goals")
            assert resp.status_code == 200
            assert "goals" in resp.json()


# ── GoalsView Component Validation ───────────────────────────────────────

class TestGoalsViewComponent:
    """Validate GoalsView has the expected structure and capabilities."""

    def test_goals_view_registered_in_router(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "Router.register('/goals', GoalsView)" in js

    def test_goals_view_exposed_as_window_global(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "window.GoalsView = GoalsView" in js

    def test_goals_view_has_hadley_api_config(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "HADLEY_API: '/api/hadley/proxy'" in js or "HADLEY_API:" in js

    def test_goals_view_has_render_method(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        # Check the GoalsView object has an async render method
        assert "async render(container)" in js

    def test_goals_view_formats_values(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "formatValue" in js
        # Check it handles all metrics
        assert "'steps'" in js
        assert "'gbp'" in js
        assert "'kg'" in js
        assert "'ml'" in js
        assert "'kcal'" in js

    def test_goals_view_has_add_modal(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "goal-title" in js
        assert "goal-type" in js
        assert "goal-category" in js
        assert "goal-metric" in js
        assert "goal-target" in js
        assert "goal-auto-source" in js

    def test_goals_view_has_log_modal(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "log-value" in js
        assert "log-note" in js

    def test_goals_view_renders_progress_bars(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "goal-progress-bar" in js
        assert "goal-progress-fill" in js

    def test_goals_view_renders_streaks(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "goal-streak" in js

    def test_goals_view_renders_trend_arrows(self, client):
        resp = client.get(f"{DASHBOARD_URL}/static/js/app.js")
        js = resp.text
        assert "goal-trend" in js
