"""Integration tests for Withings token refresh flow."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import os


@pytest.fixture(autouse=True)
def _no_cross_process_reload():
    """Disable cross-process token reload for deterministic tests.

    `_load_tokens` reads the real persistent token file on disk, which would
    clobber the tokens these tests set directly. Stubbing it to "no change"
    keeps tests exercising the refresh path rather than the cross-process
    reload-and-retry path.
    """
    with patch(
        "domains.nutrition.services.withings._load_tokens",
        return_value=False,
    ):
        yield


@pytest.fixture(autouse=True)
def _no_supabase_write():
    """Skip the Supabase write side-effect of `get_weight`.

    `_store_weight_reading` issues its own `httpx.AsyncClient().post(...)`
    call when SUPABASE creds are present. These unit tests count `post`
    calls to assert refresh behaviour, so the storage call has to be
    silenced or it shows up as a phantom extra call.
    """
    async def _noop(*_args, **_kwargs):
        return None

    with patch(
        "domains.nutrition.services.withings._store_weight_reading",
        _noop,
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_token_writes():
    """Prevent tests from clobbering the real persistent token file.

    The refresh path ends in `_save_tokens()` which writes to the shared
    LOCALAPPDATA token file used by both DiscordBot and HadleyAPI. Even
    though httpx is mocked, `_save_tokens` still runs and persists the
    mock access/refresh tokens to disk — which takes Withings offline
    until a manual re-auth. Stub it here so tests never touch real state.
    """
    with patch(
        "domains.nutrition.services.withings._save_tokens",
        lambda: None,
    ):
        yield


class TestWithingsTokenRefresh:
    """Test Withings OAuth token refresh flow."""

    @pytest.mark.asyncio
    async def test_successful_token_refresh(self):
        """Test successful token refresh when token is expired."""
        from domains.nutrition.services import withings

        # Set initial tokens
        withings._tokens = {
            "access": "expired_token",
            "refresh": "valid_refresh_token"
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()

            # First call returns expired (status != 0)
            expired_response = Mock()
            expired_response.json.return_value = {"status": 401}

            # Refresh call returns new tokens
            refresh_response = Mock()
            refresh_response.json.return_value = {
                "status": 0,
                "body": {
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token"
                }
            }

            # Retry with new token succeeds
            success_response = Mock()
            success_response.json.return_value = {
                "status": 0,
                "body": {
                    "measuregrps": [{
                        "date": 1704067200,
                        "measures": [{"value": 81500, "unit": -3}]
                    }]
                }
            }

            mock_client.post.side_effect = [expired_response, refresh_response, success_response]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Should have made 3 calls: initial, refresh, retry
            assert mock_client.post.call_count == 3

            # Should have updated tokens
            assert withings._tokens["access"] == "new_access_token"
            assert withings._tokens["refresh"] == "new_refresh_token"

            # Should return valid weight
            assert result["weight_kg"] == 81.5

    @pytest.mark.asyncio
    async def test_refresh_failure(self):
        """Test handling when token refresh fails."""
        from domains.nutrition.services import withings

        withings._tokens = {
            "access": "expired_token",
            "refresh": "invalid_refresh_token"
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()

            # First call returns expired
            expired_response = Mock()
            expired_response.json.return_value = {"status": 401}

            # Refresh call also fails
            refresh_fail_response = Mock()
            refresh_fail_response.json.return_value = {
                "status": 503,
                "error": "Invalid refresh token"
            }

            mock_client.post.side_effect = [expired_response, refresh_fail_response]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Should return error
            assert "error" in result
            assert result["weight_kg"] is None

    @pytest.mark.asyncio
    async def test_no_retry_after_refresh_and_retry(self):
        """Test that only one refresh attempt is made."""
        from domains.nutrition.services import withings

        withings._tokens = {
            "access": "expired_token",
            "refresh": "valid_refresh_token"
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()

            # Initial call: expired
            expired_response = Mock()
            expired_response.json.return_value = {"status": 401}

            # Refresh: success
            refresh_response = Mock()
            refresh_response.json.return_value = {
                "status": 0,
                "body": {
                    "access_token": "new_token",
                    "refresh_token": "new_refresh"
                }
            }

            # Retry: still fails (simulating persistent issue)
            still_expired = Mock()
            still_expired.json.return_value = {"status": 401}

            mock_client.post.side_effect = [expired_response, refresh_response, still_expired]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Should have made exactly 3 calls (no infinite loop)
            assert mock_client.post.call_count == 3

            # Should return error (no infinite retry)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_direct_success_no_refresh(self):
        """Test that refresh is not called if initial request succeeds."""
        from domains.nutrition.services import withings

        withings._tokens = {
            "access": "valid_token",
            "refresh": "refresh_token"
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()

            # Success on first try
            success_response = Mock()
            success_response.json.return_value = {
                "status": 0,
                "body": {
                    "measuregrps": [{
                        "date": 1704067200,
                        "measures": [{"value": 80000, "unit": -3}]
                    }]
                }
            }

            mock_client.post.return_value = success_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Should have made only 1 call
            assert mock_client.post.call_count == 1

            # Should return valid weight
            assert result["weight_kg"] == 80.0

    @pytest.mark.asyncio
    async def test_environment_update_on_refresh(self):
        """Test that environment variables are updated on successful refresh."""
        from domains.nutrition.services import withings

        # Store original env values
        original_access = os.environ.get("WITHINGS_ACCESS_TOKEN")
        original_refresh = os.environ.get("WITHINGS_REFRESH_TOKEN")

        try:
            withings._tokens = {
                "access": "old_token",
                "refresh": "old_refresh"
            }

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()

                # Expired then refresh success
                expired_response = Mock()
                expired_response.json.return_value = {"status": 401}

                refresh_response = Mock()
                refresh_response.json.return_value = {
                    "status": 0,
                    "body": {
                        "access_token": "env_updated_access",
                        "refresh_token": "env_updated_refresh"
                    }
                }

                success_response = Mock()
                success_response.json.return_value = {
                    "status": 0,
                    "body": {"measuregrps": [{"date": 1704067200, "measures": [{"value": 80000, "unit": -3}]}]}
                }

                mock_client.post.side_effect = [expired_response, refresh_response, success_response]
                mock_client_class.return_value.__aenter__.return_value = mock_client

                await withings.get_weight()

                # Check env was updated
                assert os.environ.get("WITHINGS_ACCESS_TOKEN") == "env_updated_access"
                assert os.environ.get("WITHINGS_REFRESH_TOKEN") == "env_updated_refresh"

        finally:
            # Restore original env
            if original_access:
                os.environ["WITHINGS_ACCESS_TOKEN"] = original_access
            if original_refresh:
                os.environ["WITHINGS_REFRESH_TOKEN"] = original_refresh


class TestWithingsCrossProcessReload:
    """Cover the cross-process desync fix: sibling process refreshed the
    token and wrote it to disk; we should reload from file and retry
    without burning a refresh_token call (which would fail with 'invalid
    refresh_token' since our in-memory one was rotated out)."""

    @pytest.mark.asyncio
    async def test_reload_from_file_on_401_skips_refresh(self, monkeypatch):
        """On 401, if the persistent file has a newer refresh_token than
        what's in memory, retry with the reloaded access_token and do NOT
        issue an OAuth refresh."""
        from domains.nutrition.services import withings

        # Disable the autouse fixture for this test so the real _load_tokens
        # runs — we want to verify it's invoked on the 401 path.
        # (Autouse is still active; instead we monkey-patch a fake that
        # simulates a sibling process having just written new tokens.)
        def fake_load_tokens(quiet: bool = False) -> bool:
            withings._tokens["access"] = "sibling_refreshed_access"
            withings._tokens["refresh"] = "sibling_refreshed_refresh"
            return True  # refresh_token changed vs what was in memory

        monkeypatch.setattr(
            "domains.nutrition.services.withings._load_tokens",
            fake_load_tokens,
        )

        withings._tokens = {
            "access": "our_stale_access",
            "refresh": "our_stale_refresh",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            expired_response = Mock()
            expired_response.json.return_value = {"status": 401}

            success_response = Mock()
            success_response.json.return_value = {
                "status": 0,
                "body": {
                    "measuregrps": [{
                        "date": 1704067200,
                        "measures": [{"value": 80000, "unit": -3}],
                    }]
                },
            }

            mock_client.post.side_effect = [expired_response, success_response]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Only 2 POSTs: initial 401 + retry with reloaded token.
            # Crucially NO third call for /v2/oauth2 refresh.
            assert mock_client.post.call_count == 2
            retry_call = mock_client.post.call_args_list[1]
            assert retry_call.kwargs["headers"]["Authorization"] == (
                "Bearer sibling_refreshed_access"
            )
            assert result["weight_kg"] == 80.0
