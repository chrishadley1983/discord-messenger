"""Channel MCP-init watchdog — transcript parsing and the restart decision."""
from __future__ import annotations

from domains.peterbot import channel_mcp_scan as scan
from domains.peterbot import channel_mcp_watchdog as wd

NL = chr(10)
# Real shape: ToolSearch's tool_result content, entries separated by "; " and a
# literal backslash-n (two characters) in the raw file.
FAIL_LINE = (
    '{"parentUuid":"x","type":"user","timestamp":"2026-09-06T02:30:12.812Z","cwd":"/home/chris_hadley/peterbot",'
    '"sessionId":"d3b7322e","message":{"role":"user","content":[{"type":"tool_result","content":"No matching '
    'deferred tools found. Note: these configured MCP servers failed to connect, so their tools are unavailable '
    'for this session: playwright (CONNECT_TIMEOUT): \\"MCP server playwright connection timed out after 30000ms\\"; '
    '\\ncontext7 (CONNECT_TIMEOUT): \\"MCP server context7 connection timed out after 30000ms\\"; '
    'supabase (CONNECT_TIMEOUT): \\"MCP server supabase connection timed out after 30000ms\\""}]}}' + NL
)
JOBS_LINE = (
    '{"type":"user","timestamp":"2026-09-06T02:30:09.000Z","message":{"role":"user","content":'
    '"<channel source=\\"jobs-channel\\" job_id=\\"abc\\" skill=\\"vercel-usage\\">run</channel>"}}' + NL
)
WHATSAPP_LINE = (
    '{"type":"user","timestamp":"2026-09-06T02:30:09.000Z","message":{"role":"user","content":'
    '"<channel source=\\"whatsapp\\" phone=\\"447\\" sender=\\"Chris\\">hi</channel>"}}' + NL
)
PETER_LINE = (
    '{"type":"assistant","timestamp":"2026-09-06T07:13:26.000Z","message":{"content":[{"type":"tool_use",'
    '"name":"mcp__peter-channel__reply","input":{"text":"hi"}}]}}' + NL
)
# A Read of this very test file: the same words, but as numbered lines inside a
# content string — must NOT count as a failure.
READ_OF_TESTS_LINE = (
    '{"type":"user","timestamp":"2026-09-06T02:31:00Z","message":{"content":[{"type":"tool_result","content":'
    '"     9\\t    \'deferred tools found. Note: these configured MCP servers failed to connect, so their tools are unavailable \'\\n'
    '    10\\t    \'for this session: playwright (CONNECT_TIMEOUT): MCP server playwright connection timed out after 30000ms\'"}]}}' + NL
)


class TestParse:
    def test_identifies_channel_and_failed_servers(self):
        out = scan.parse_text(JOBS_LINE + FAIL_LINE)
        assert out["channel"] == "jobs-channel"
        assert out["mcp_failed"] is True
        assert out["failed_servers"] == ["playwright", "context7", "supabase"]
        assert abs(out["first_ts"] - 1788661809.0) < 1  # 2026-09-06T02:30:09Z

    def test_clean_session(self):
        out = scan.parse_text(PETER_LINE)
        assert out["channel"] == "peter-channel" and out["mcp_failed"] is False and out["failed_servers"] == []

    def test_whatsapp_source_tag_is_bare_whatsapp(self):
        assert scan.parse_text(WHATSAPP_LINE)["channel"] == "whatsapp-channel"

    def test_source_tag_outranks_prose_mention_of_another_channel(self):
        prose = '{"type":"assistant","timestamp":"2026-09-06T02:31:00Z","message":{"content":"restart server:jobs-channel-sonnet please"}}'
        assert scan.parse_text(JOBS_LINE + prose + NL)["channel"] == "jobs-channel"

    def test_banner_prefers_longest_name(self):
        assert scan.parse_text('{"timestamp":"2026-09-06T00:00:00Z"} server:jobs-channel-sonnet')["channel"] == "jobs-channel-sonnet"

    def test_identity_only_from_head(self):
        filler = (NL.join('{"type":"assistant","timestamp":"2026-09-06T00:00:01Z","message":{"content":"x"}}'
                          for _ in range(scan.HEAD_LINES)) + NL)
        assert scan.parse_text(filler + JOBS_LINE)["channel"] is None

    def test_reading_source_files_is_not_a_failure(self):
        out = scan.parse_text(JOBS_LINE + READ_OF_TESTS_LINE)
        assert out["mcp_failed"] is False and out["failed_servers"] == []

    def test_scraper_timeout_text_is_not_a_failure(self):
        line = ('{"type":"user","timestamp":"2026-09-06T02:31:00Z","message":{"content":[{"type":"tool_result",'
                '"content":"curl: (28) connection timed out after 30000 ms"}]}}' + NL)
        assert scan.parse_text(JOBS_LINE + line)["mcp_failed"] is False

    def test_unknown_channel(self):
        assert scan.parse_text('{"timestamp":"2026-09-06T00:00:00Z"}' + NL)["channel"] is None


def _row(channel, sid, first_ts, mtime, failed, servers=("supabase",)):
    return {"channel": channel, "session_id": sid, "file": f"{sid}.jsonl", "first_ts": first_ts,
            "mtime": mtime, "mcp_failed": failed, "failed_servers": list(servers) if failed else []}


NOW = 1_800_000_000.0
CREATED = {"jobs-channel": NOW - 3600}


class TestDecide:
    def test_restarts_current_dead_session_between_turns(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 600, True)]
        acts = wd.decide(scan_, CREATED, {"jobs-channel": False}, {}, NOW)
        assert [a["channel"] for a in acts] == ["jobs-channel"]
        assert acts[0]["session_id"] == "cur" and "supabase" in acts[0]["reason"]

    def test_previous_sessions_transcript_is_ignored(self):
        # File started before this tmux session existed → belongs to the old session.
        scan_ = [_row("jobs-channel", "old", NOW - 7200, NOW - 10, True)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": False}, {}, NOW) == []

    def test_newest_transcript_wins(self):
        scan_ = [_row("jobs-channel", "a", NOW - 3000, NOW - 2000, True),
                 _row("jobs-channel", "b", NOW - 2500, NOW - 100, False)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": False}, {}, NOW) == []

    def test_never_restarts_mid_turn(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 5, True)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": True}, {}, NOW) == []

    def test_busy_with_long_running_tool_is_still_mid_turn(self):
        # 10-minute job with one long Bash: transcript silent 9.5 min, health still busy.
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 570, True)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": True}, {}, NOW) == []

    def test_stuck_busy_reading_is_overridden_after_long_silence(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - wd.STALE_BUSY_S - 1, True)]
        assert len(wd.decide(scan_, CREATED, {"jobs-channel": True}, {}, NOW)) == 1

    def test_unknown_busy_waits_for_quiet(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 30, True)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": None}, {}, NOW) == []
        scan_[0]["mtime"] = NOW - 300
        assert len(wd.decide(scan_, CREATED, {"jobs-channel": None}, {}, NOW)) == 1

    def test_one_restart_per_session(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 600, True)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": False}, {"jobs-channel": "cur"}, NOW) == []

    def test_channel_without_tmux_session_is_left_to_launch_watchdog(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 600, True)]
        assert wd.decide(scan_, {}, {"jobs-channel": False}, {}, NOW) == []

    def test_clean_session_no_action(self):
        scan_ = [_row("jobs-channel", "cur", NOW - 3000, NOW - 600, False)]
        assert wd.decide(scan_, CREATED, {"jobs-channel": False}, {}, NOW) == []


class TestBudgetAndHealth:
    def test_budget_allows_three_then_blocks(self):
        assert wd.budget_ok([], NOW)
        assert wd.budget_ok([NOW - 100, NOW - 200], NOW)
        assert not wd.budget_ok([NOW - 100, NOW - 200, NOW - 300], NOW)
        # old restarts fall out of the window
        assert wd.budget_ok([NOW - 100, NOW - 200, NOW - wd.RESTART_WINDOW_S - 1], NOW)

    def test_channel_busy_shapes(self, monkeypatch):
        class R:
            def __init__(self, d): self.d = d
            def json(self): return self.d
        monkeypatch.setattr(wd.httpx, "get", lambda url, timeout: R({"messages_in": 3, "messages_out": 2}))
        assert wd.channel_busy("peter-channel") is True
        monkeypatch.setattr(wd.httpx, "get", lambda url, timeout: R({"pending_jobs": 0}))
        assert wd.channel_busy("jobs-channel") is False
        monkeypatch.setattr(wd.httpx, "get", lambda url, timeout: R({"pending": "garbage"}))
        assert wd.channel_busy("extract-channel") is None  # malformed → unknown, never raises
        monkeypatch.setattr(wd.httpx, "get", lambda url, timeout: R({"status": "ok"}))
        assert wd.channel_busy("whatsapp-channel") is None

    def test_check_and_restart_marks_handled_only_on_success(self, monkeypatch):
        monkeypatch.setattr(wd, "scan_transcripts", lambda: [_row("jobs-channel", "cur", NOW - 3000, NOW - 600, True)])
        monkeypatch.setattr(wd, "tmux_session_created", lambda: dict(CREATED))
        monkeypatch.setattr(wd, "channel_busy", lambda name: False)
        monkeypatch.setattr(wd.time, "time", lambda: NOW)
        wd._handled.clear(); wd._restarts.clear()
        calls = []
        import domains.peterbot.channel_auth as ca
        monkeypatch.setattr(ca, "force_restart_channel", lambda name, mark_relaunched=None, reason=None: calls.append(name) or False)
        assert wd.check_and_restart()["action"] == "none"
        assert wd._handled == {}  # cooldown-skipped → retried next tick
        monkeypatch.setattr(ca, "force_restart_channel", lambda name, mark_relaunched=None, reason=None: calls.append(name) or True)
        assert wd.check_and_restart()["restarted"] == ["jobs-channel"]
        assert wd._handled == {"jobs-channel": "cur"} and wd._restarts["jobs-channel"] == [NOW]
        assert wd.check_and_restart()["action"] == "none"  # same session: no second restart
        wd._handled.clear(); wd._restarts.clear()
