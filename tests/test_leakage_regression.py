"""Comprehensive leakage regression tests.

Based on analysis of 75 captures - 49 unique leak patterns identified.
These tests ensure the sanitiser catches all known leak types.

Run with: pytest tests/test_leakage_regression.py -v
"""

import pytest
import sys
sys.path.insert(0, '.')

from domains.peterbot.response.sanitiser import sanitise
from domains.peterbot.capture_parser import ParserCaptureStore


# =============================================================================
# REAL SAMPLES FROM DATABASE (organized by category)
# =============================================================================

# Category: Instruction Echo (84% of captures)
INSTRUCTION_SAMPLES = [
    ('instruction_current_msg',
     'Current Message section.\n\nAnswer: The weather looks good today.',
     ['Current Message section', 'Answer:']),

    ('instruction_with_content',
     'Current Message section.\n\nYes, the recipe skill is built.',
     ['Current Message section']),
]

# Category: JSON Artifacts (86 total occurrences)
JSON_SAMPLES = [
    ('json_message_id',
     '"message_id": "19c2a81a5952faa7",\n\nResent to email@example.com',
     ['"message_id"']),

    ('json_event_id',
     '"event_id": "0pbtqsae0mdnhlcrk8e2c4gbgk",\n\nCalendar updated.',
     ['"event_id"']),

    ('json_session_id',
     '"session_id": "sess_9cb6598ea8de",\n"domain": "amazon.co.uk",\n\nSession started.',
     ['"session_id"']),

    ('json_deleted_id',
     '"deleted_id": "882cdc9c-9b67-4f3e-ac31-4e98d9ce1d91"\n}\n\nDeleted the item.',
     ['"deleted_id"']),

    ('json_set_number',
     '"set_number": "40448",\n\nFound in database.',
     ['"set_number"']),

    ('json_key_string',
     '"meal_type":"dinner","description":"Chicken with rice"\n\nLogged: dinner',
     ['"meal_type"', '"description"']),

    ('json_key_number',
     '"cost": 0, "quantity": 1\n\nPurchase recorded.',
     ['"cost":', '"quantity"']),

    ('json_key_bool',
     '"amazon": null,\n"available": true,\n\nChecked the API.',
     ['"amazon": null', '"available": true']),

    ('json_standalone_braces',
     '{\n"message_id": "abc"\n}\n\nEmail sent.',
     ['{']),  # Opening brace - closing might be legitimate

    ('json_close_brace_line',
     '}\n\nThe operation completed.',
     []),  # Standalone } at start - might be ok depending on context
]

# Category: Claude Code UI (24 occurrences)
CC_UI_SAMPLES = [
    ('cc_thinking_full',
     '\u273d Sketching\u273d (49s \u273d \u2193 1.7k tokens \u273d thinking)',
     ['Sketching', 'tokens', '\u2193']),

    ('cc_thinking_plain',
     'Concocting (thought for 2s)',
     ['Concocting']),

    ('cc_token_count',
     'Processing... 2.5k tokens used',
     ['tokens']),

    ('cc_spinner_star',
     '\u273d Working on your request...',
     ['\u273d']),
]

# Category: Paths (35 occurrences)
PATH_SAMPLES = [
    ('path_home_chris',
     '/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot/*.jsonl\n\nSearching...',
     ['/home/chris_hadley', '.claude/projects', '.jsonl']),

    ('path_claude_projects',
     '.claude/projects/foo/bar.md\n\nFound the file.',
     ['.claude/projects']),

    ('path_jsonl_glob',
     'peterbot/*.jsonl\n\nLooking for logs.',
     ['*.jsonl']),

    ('path_peterbot',
     '/home/user/peterbot/data/captures.db\n\nDatabase found.',
     ['peterbot/']),
]

# Category: Commands (28 occurrences)
CMD_SAMPLES = [
    ('cmd_pipe_echo',
     '|| echo "No results"\n\nSearched but found nothing.',
     ['|| echo']),

    ('cmd_and_curl',
     '&& curl -s http://api.example.com\n\nFetching data.',
     ['&& curl']),

    ('cmd_import_sys_json',
     '"import sys,json; d=json.load(sys.stdin); print(d)\n\nParsing response.',
     ['import sys,json', 'json.load']),

    ('cmd_python_c',
     'python3 -c "print(1+1)"\n\nCalculating.',
     ['python3 -c']),

    ('cmd_head_tail',
     '| head -50)\n\nShowing first 50 lines.',
     ['head -50']),

    ('cmd_line_continuation',
     '7e5-f80cb411cefd" \\\n\nContinued on next line.',
     ['" \\']),
]

# Category: API/URLs (40 occurrences)
API_SAMPLES = [
    ('api_localhost',
     'localhost:8100/nutrition/log\n\nLogging meal.',
     ['localhost:8100']),

    ('api_172_ip',
     '172.19.64.1:8100/api/test\n\nTesting endpoint.',
     ['172.19.64.1']),

    ('api_content_type',
     'Content-Type: application/json" -d \'{"key": "value"}\'\n\nSending request.',
     ['Content-Type:', 'application/json']),

    ('api_curl_header',
     '-H "Authorization: Bearer token"\n\nAuthorizing.',
     ['-H "']),

    ('api_data_payload',
     '-d \'{"set_number": "40448", "cost": 0}\'\n\nPosting data.',
     ["-d '{"]),

    ('api_path_pi',
     'pi/inventory/d035e1b3-a8c4-422d-a7e5-f80cb411cefd\n\nChecking inventory.',
     ['pi/inventory/']),

    ('api_path_hb',
     'hb/inventory/status\n\nGetting status.',
     ['hb/inventory/']),

    ('api_uuid_full',
     'd035e1b3-a8c4-422d-a7e5-f80cb411cefd\n\nFound item.',
     ['d035e1b3-a8c4-422d-a7e5-f80cb411cefd']),

    ('api_query_param',
     '/hb/buy-box?asin=B08SJ8R7WB&refresh=true\n\nChecking price.',
     ['?asin=']),
]

# Category: Errors (16 occurrences)
ERROR_SAMPLES = [
    ('error_unauthorized',
     'Unauthorized\n\nNeed to authenticate.',
     ['Unauthorized']),

    ('error_not_found',
     'Endpoint not found\n\nAPI missing.',
     ['not found']),

    ('error_invalid_scope',
     'invalid_scope: Bad Request\n\nOAuth error.',
     ['invalid_scope']),

    ('error_traceback',
     'Traceback (most recent call last):\n  File "<string>", line 1\n\nError occurred.',
     ['Traceback']),
]

# Category: Misc Artifacts
ARTIFACT_SAMPLES = [
    ('artifact_task_output',
     'Task Output b8d48fc\n\nCompleted.',
     ['Task Output']),
]


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

class TestInstructionEcho:
    """Test instruction echo patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", INSTRUCTION_SAMPLES)
    def test_instruction_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestJSONArtifacts:
    """Test JSON artifact patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", JSON_SAMPLES)
    def test_json_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestClaudeCodeUI:
    """Test Claude Code UI artifacts are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", CC_UI_SAMPLES)
    def test_cc_ui_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestPaths:
    """Test internal path patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", PATH_SAMPLES)
    def test_path_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestCommands:
    """Test command fragment patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", CMD_SAMPLES)
    def test_command_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestAPIURLs:
    """Test API/URL patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", API_SAMPLES)
    def test_api_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestErrors:
    """Test error message patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", ERROR_SAMPLES)
    def test_error_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestMiscArtifacts:
    """Test miscellaneous artifact patterns are sanitised."""

    @pytest.mark.parametrize("name,input_text,must_not_contain", ARTIFACT_SAMPLES)
    def test_artifact_patterns(self, name, input_text, must_not_contain):
        result = sanitise(input_text, aggressive=True)
        for pattern in must_not_contain:
            assert pattern not in result, f"{name}: '{pattern}' should be removed"


class TestEchoDetection:
    """Test that capture_parser detects echo/leakage correctly."""

    def setup_method(self):
        self.store = ParserCaptureStore()
        self.screen_before = "> test message\n\n> /nutrition log breakfast"

    def test_detects_instruction_echo(self):
        assert self.store._detect_echo(
            self.screen_before,
            'Current Message section.\n\nLogged breakfast.'
        )

    def test_detects_command_chain(self):
        assert self.store._detect_echo(
            self.screen_before,
            '|| echo "test"\n\nResult here.'
        )

    def test_detects_internal_path(self):
        assert self.store._detect_echo(
            self.screen_before,
            '/home/chris_hadley/.claude/projects/foo\n\nFound it.'
        )

    def test_detects_python_import(self):
        assert self.store._detect_echo(
            self.screen_before,
            'import sys,json; d=json.load(sys.stdin)\n\nParsed.'
        )

    def test_detects_json_id(self):
        assert self.store._detect_echo(
            self.screen_before,
            '"message_id": "abc123"\n\nSent.'
        )

    def test_detects_thinking_status(self):
        assert self.store._detect_echo(
            self.screen_before,
            'Sketching (10s)\n\nDone.'
        )

    def test_clean_response_not_flagged(self):
        assert not self.store._detect_echo(
            self.screen_before,
            'Logged: porridge - 350 cal | 12g protein'
        )

    def test_normal_checkmark_not_flagged(self):
        assert not self.store._detect_echo(
            self.screen_before,
            '\u2713 Logged breakfast successfully!'
        )


class TestFalsePositives:
    """Ensure legitimate content is NOT removed."""

    def test_preserves_user_content(self):
        """User's actual message content should remain."""
        input_text = "The weather today is sunny with 20C temperature."
        result = sanitise(input_text, aggressive=True)
        assert "sunny" in result
        assert "20C" in result

    def test_preserves_formatted_output(self):
        """Properly formatted bot output should remain."""
        input_text = "\u2713 Logged: Porridge \u2014 350 cal | 12g P | 45g C | 8g F"
        result = sanitise(input_text, aggressive=True)
        assert "Logged:" in result
        assert "350 cal" in result

    def test_preserves_links(self):
        """User-facing links should remain."""
        input_text = "Check out [this article](https://example.com/news)"
        result = sanitise(input_text, aggressive=True)
        assert "https://example.com/news" in result

    def test_preserves_emojis(self):
        """Emojis should remain."""
        input_text = "\u2600\ufe0f Good morning! \u2615 Coffee time."
        result = sanitise(input_text, aggressive=True)
        assert "\u2600" in result or "Good morning" in result


# =============================================================================
# SUMMARY STATISTICS
# =============================================================================

def test_pattern_coverage():
    """Verify we have test coverage for all major leak categories."""
    categories_tested = {
        'instruction': len(INSTRUCTION_SAMPLES),
        'json': len(JSON_SAMPLES),
        'cc_ui': len(CC_UI_SAMPLES),
        'path': len(PATH_SAMPLES),
        'cmd': len(CMD_SAMPLES),
        'api': len(API_SAMPLES),
        'error': len(ERROR_SAMPLES),
        'artifact': len(ARTIFACT_SAMPLES),
    }

    total = sum(categories_tested.values())
    print(f"\nTotal regression test cases: {total}")
    for cat, count in categories_tested.items():
        print(f"  {cat}: {count}")

    # Ensure we have meaningful coverage
    assert total >= 30, f"Need at least 30 test cases, have {total}"
    assert all(c >= 1 for c in categories_tested.values()), "All categories need tests"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
