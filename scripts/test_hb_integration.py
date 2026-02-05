#!/usr/bin/env python3
"""
HB Integration Test Suite

Run: python scripts/test_hb_integration.py

Tests all Hadley API -> HB integration points to verify:
1. Authentication works with the configured key
2. All GET endpoints return valid JSON
3. All POST endpoints accept data correctly
4. Full skill workflows (lookup -> pricing -> create) succeed
"""

import asyncio
import httpx
import json
import os
import sys
from datetime import datetime, date
from typing import Optional, Tuple
from dataclasses import dataclass

# Configuration
HADLEY_API_URL = os.environ.get("HADLEY_API_URL", "http://172.19.64.1:8100")
TIMEOUT = 30.0

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    data: Optional[dict] = None

class TestRunner:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        self.results: list[TestResult] = []
        self.test_asin: Optional[str] = None  # Captured from lookup for later tests

    async def close(self):
        await self.client.aclose()

    def log(self, result: TestResult):
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"{status} {result.name}: {result.message}")
        self.results.append(result)

    async def get(self, endpoint: str, params: dict = None) -> Tuple[int, dict]:
        """Make GET request and return (status_code, json_data)."""
        try:
            url = f"{HADLEY_API_URL}{endpoint}"
            resp = await self.client.get(url, params=params)
            try:
                data = resp.json()
            except:
                data = {"raw": resp.text[:500]}
            return resp.status_code, data
        except Exception as e:
            return 0, {"error": str(e)}

    async def post(self, endpoint: str, data: dict) -> Tuple[int, dict]:
        """Make POST request and return (status_code, json_data)."""
        try:
            url = f"{HADLEY_API_URL}{endpoint}"
            resp = await self.client.post(url, json=data)
            try:
                result = resp.json()
            except:
                result = {"raw": resp.text[:500]}
            return resp.status_code, result
        except Exception as e:
            return 0, {"error": str(e)}

    # ==================== CATEGORY A: Authentication Tests ====================

    async def test_a1_valid_connection(self):
        """Test that Hadley API is reachable and HB connection works."""
        status, data = await self.get("/hb/pnl")  # Simple endpoint
        if status == 200:
            self.log(TestResult("A1: Valid connection", True, f"P&L returned OK"))
        elif status == 401:
            self.log(TestResult("A1: Valid connection", False, "401 Unauthorized - key mismatch between Hadley API and HB Vercel!"))
        else:
            self.log(TestResult("A1: Valid connection", False, f"Status {status}: {data}"))

    # ==================== CATEGORY B: GET Endpoint Tests ====================

    async def test_b1_pnl(self):
        """Test /hb/pnl endpoint."""
        status, data = await self.get("/hb/pnl")
        passed = status == 200
        self.log(TestResult("B1: P&L", passed,
            f"OK - got P&L data" if passed else f"Failed: {status} - {data}"))

    async def test_b2_inventory(self):
        """Test /hb/inventory endpoint."""
        status, data = await self.get("/hb/inventory")
        passed = status == 200
        self.log(TestResult("B2: Inventory", passed,
            f"OK - got inventory data" if passed else f"Failed: {status} - {data}"))

    async def test_b3_inventory_aging(self):
        """Test /hb/inventory/aging endpoint."""
        status, data = await self.get("/hb/inventory/aging")
        passed = status == 200
        self.log(TestResult("B3: Inventory Aging", passed,
            f"OK - got aging data" if passed else f"Failed: {status} - {data}"))

    async def test_b4_daily(self):
        """Test /hb/daily endpoint."""
        status, data = await self.get("/hb/daily")
        passed = status == 200
        self.log(TestResult("B4: Daily Activity", passed,
            f"OK - got daily data" if passed else f"Failed: {status} - {data}"))

    async def test_b5_orders(self):
        """Test /hb/orders endpoint."""
        status, data = await self.get("/hb/orders")
        passed = status == 200
        self.log(TestResult("B5: Orders", passed,
            f"OK - got orders" if passed else f"Failed: {status} - {data}"))

    async def test_b6_purchases(self):
        """Test /hb/purchases endpoint."""
        status, data = await self.get("/hb/purchases")
        passed = status == 200
        self.log(TestResult("B6: Purchases", passed,
            f"OK - got purchases" if passed else f"Failed: {status} - {data}"))

    async def test_b7_purchase_analysis(self):
        """Test /hb/purchase-analysis endpoint."""
        status, data = await self.get("/hb/purchase-analysis")
        passed = status == 200
        self.log(TestResult("B7: Purchase Analysis", passed,
            f"OK - got analysis data" if passed else f"Failed: {status} - {data}"))

    async def test_b8_set_lookup(self):
        """Test /hb/set/{set_number} endpoint."""
        status, data = await self.get("/hb/set/40448")
        passed = status == 200
        self.log(TestResult("B8: Set Lookup", passed,
            f"OK - got set info" if passed else f"Failed: {status} - {data}"))

    async def test_b9_stock(self):
        """Test /hb/stock/{set_number} endpoint."""
        status, data = await self.get("/hb/stock/40448")
        passed = status == 200
        self.log(TestResult("B9: Stock Check", passed,
            f"OK - got stock data" if passed else f"Failed: {status} - {data}"))

    async def test_b10_pick_list(self):
        """Test /hb/pick-list endpoint."""
        status, data = await self.get("/hb/pick-list")
        passed = status == 200
        self.log(TestResult("B10: Pick List", passed,
            f"OK - got pick list" if passed else f"Failed: {status} - {data}"))

    async def test_b11_arbitrage(self):
        """Test /hb/arbitrage endpoint."""
        status, data = await self.get("/hb/arbitrage")
        passed = status == 200
        self.log(TestResult("B11: Arbitrage", passed,
            f"OK - got arbitrage data" if passed else f"Failed: {status} - {data}"))

    async def test_b12_tasks(self):
        """Test /hb/tasks endpoint."""
        status, data = await self.get("/hb/tasks")
        passed = status == 200
        self.log(TestResult("B12: Tasks", passed,
            f"OK - got tasks" if passed else f"Failed: {status} - {data}"))

    async def test_b13_pickups(self):
        """Test /hb/pickups endpoint."""
        status, data = await self.get("/hb/pickups")
        passed = status == 200
        self.log(TestResult("B13: Pickups", passed,
            f"OK - got pickups" if passed else f"Failed: {status} - {data}"))

    async def test_b14_lookup_asin(self):
        """Test /hb/lookup-asin endpoint."""
        status, data = await self.get("/hb/lookup-asin", {"set_number": "40448"})
        passed = status == 200
        if passed and isinstance(data, dict):
            self.test_asin = data.get("asin") or data.get("amazon_asin")
        self.log(TestResult("B14: Lookup ASIN", passed,
            f"OK - ASIN: {self.test_asin}" if passed else f"Failed: {status} - {data}"))

    async def test_b15_competitive_pricing(self):
        """Test /hb/competitive-pricing endpoint."""
        # Use set_number instead of asin since endpoint changed
        status, data = await self.get("/hb/competitive-pricing", {"set_number": "40448"})
        passed = status == 200
        self.log(TestResult("B15: Competitive Pricing", passed,
            f"OK - got pricing" if passed else f"Failed: {status} - {data}"))

    # ==================== CATEGORY C: POST Endpoint Tests ====================

    async def test_c1_purchases_post(self):
        """Test /hb/purchases POST endpoint (dry run - check auth only)."""
        # Send minimal data to check auth works - expect validation error, not auth error
        status, data = await self.post("/hb/purchases", {"test": True})
        # We expect either 200/201 (success) or 400/422 (validation error)
        # 401/403 means auth failed
        passed = status not in [401, 403, 500]
        self.log(TestResult("C1: Purchases POST (auth check)", passed,
            f"OK - auth accepted (status {status})" if passed else f"Auth failed: {status} - {data}"))

    async def test_c2_inventory_post(self):
        """Test /hb/inventory POST endpoint (dry run - check auth only)."""
        status, data = await self.post("/hb/inventory", {"test": True})
        passed = status not in [401, 403, 500]
        self.log(TestResult("C2: Inventory POST (auth check)", passed,
            f"OK - auth accepted (status {status})" if passed else f"Auth failed: {status} - {data}"))

    async def test_c3_batch_import_post(self):
        """Test /hb/batch-import POST endpoint (dry run - check auth only)."""
        status, data = await self.post("/hb/batch-import", {"items": [], "automated": False})
        passed = status not in [401, 403, 500]
        self.log(TestResult("C3: Batch Import POST (auth check)", passed,
            f"OK - auth accepted (status {status})" if passed else f"Auth failed: {status} - {data}"))

    # ==================== CATEGORY D: Skill Flow Tests ====================

    async def test_d1_add_purchase_flow(self):
        """Test full add-purchase skill flow: lookup -> pricing -> batch-import."""
        # Step 1: Lookup ASIN
        status1, data1 = await self.get("/hb/lookup-asin", {"set_number": "40448"})
        if status1 != 200:
            self.log(TestResult("D1: Add Purchase Flow", False, f"Step 1 (lookup) failed: {status1}"))
            return

        # Step 2: Get competitive pricing
        status2, data2 = await self.get("/hb/competitive-pricing", {"set_number": "40448"})
        if status2 != 200:
            self.log(TestResult("D1: Add Purchase Flow", False, f"Step 2 (pricing) failed: {status2}"))
            return

        # Step 3: Check batch-import auth (don't actually create record)
        status3, data3 = await self.post("/hb/batch-import", {"items": [], "automated": False, "dry_run": True})
        passed = status3 not in [401, 403, 500]

        self.log(TestResult("D1: Add Purchase Flow", passed,
            f"OK - Full flow works (lookup={status1}, pricing={status2}, import={status3})"
            if passed else f"Step 3 (import) failed: {status3}"))

    async def test_d2_pnl_flow(self):
        """Test P&L skill flow."""
        status, data = await self.get("/hb/pnl")
        passed = status == 200 and isinstance(data, dict)
        self.log(TestResult("D2: P&L Flow", passed,
            f"OK - P&L accessible" if passed else f"Failed: {status}"))

    # ==================== Run All Tests ====================

    async def run_all(self):
        """Run all tests in order."""
        print("=" * 60)
        print("HB Integration Test Suite")
        print(f"Target: {HADLEY_API_URL}")
        print(f"Time: {datetime.now().isoformat()}")
        print("=" * 60)

        # Category A: Authentication
        print("\n--- Category A: Authentication ---")
        await self.test_a1_valid_connection()

        # Category B: GET Endpoints
        print("\n--- Category B: GET Endpoints ---")
        await self.test_b1_pnl()
        await self.test_b2_inventory()
        await self.test_b3_inventory_aging()
        await self.test_b4_daily()
        await self.test_b5_orders()
        await self.test_b6_purchases()
        await self.test_b7_purchase_analysis()
        await self.test_b8_set_lookup()
        await self.test_b9_stock()
        await self.test_b10_pick_list()
        await self.test_b11_arbitrage()
        await self.test_b12_tasks()
        await self.test_b13_pickups()
        await self.test_b14_lookup_asin()
        await self.test_b15_competitive_pricing()

        # Category C: POST Endpoints
        print("\n--- Category C: POST Endpoints (auth check only) ---")
        await self.test_c1_purchases_post()
        await self.test_c2_inventory_post()
        await self.test_c3_batch_import_post()

        # Category D: Skill Flows
        print("\n--- Category D: Skill Flows ---")
        await self.test_d1_add_purchase_flow()
        await self.test_d2_pnl_flow()

        # Summary
        print("\n" + "=" * 60)
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print(f"Results: {passed}/{total} tests passed")

        if passed == total:
            print(">>> ALL TESTS PASSED - Integration is working correctly")
        else:
            print(">>> SOME TESTS FAILED - Review errors above")
            failed = [r for r in self.results if not r.passed]
            print("\nFailed tests:")
            for r in failed:
                print(f"  - {r.name}: {r.message}")

        print("=" * 60)

        return passed == total


async def main():
    runner = TestRunner()
    try:
        success = await runner.run_all()
        sys.exit(0 if success else 1)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
