"""Sanitiser - Stage 1 of the Response Processing Pipeline.

Strips Claude Code terminal artifacts that should never reach Discord users.
Based on RESPONSE.md Section 3.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SanitiserResult:
    """Result of sanitisation with metadata."""
    content: str
    rules_applied: list[str] = field(default_factory=list)
    original_length: int = 0
    final_length: int = 0


# =============================================================================
# SANITISER RULES - Ordered by processing priority (Section 3.2)
# =============================================================================

SANITISER_RULES = [
    # 1. ANSI Escape Codes (MUST be first - interferes with other patterns)
    {
        'name': 'ansi_codes',
        'pattern': re.compile(r'\x1b\[[0-9;]*m'),
        'replacement': '',
        'description': 'Terminal colour/style escape codes'
    },

    # 2. CC Session Headers (box-drawing characters)
    {
        'name': 'cc_session_header',
        'pattern': re.compile(r'^[╭╮╰╯│─┌┐└┘├┤┬┴┼].*$', re.MULTILINE),
        'replacement': '',
        'description': 'CC box-drawing session headers and borders'
    },

    # 3. CC Tool Use Indicators
    {
        'name': 'cc_tool_indicators',
        'pattern': re.compile(
            r'^(?:⎿|├|└|⏵)\s*'
            r'(?:Read|Write|Edit|Bash|Search|Fetch|Glob|Grep|WebSearch|WebFetch|'
            r'TodoRead|TodoWrite|Task|Skill|MultiTool|NotebookEdit|ListFiles|'
            r'AskUser|mcp__[^\s]+|brave_[^\s]+).*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'CC tool invocation lines'
    },

    # 4. CC Bullet Markers
    {
        'name': 'cc_bullet_markers',
        'pattern': re.compile(r'^[⏺●]\s*', re.MULTILINE),
        'replacement': '',
        'description': 'CC bullet point markers'
    },

    # 5. CC Token/Cost Summaries
    {
        'name': 'cc_token_summary',
        'pattern': re.compile(
            r'^(?:Total tokens|Cost|Input|Output|Cache|'
            r'\d+[kK]?\s*(?:tokens?|input|output)|'
            r'(?:cost|tokens)\s*:\s*[\$\d]).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC token usage and cost lines'
    },

    # 6. CC Status Lines
    {
        'name': 'cc_status_lines',
        'pattern': re.compile(
            r'^(?:Compacting conversation|Continuing|Session resumed|'
            r'Creating.*\(\d+[kK]?\s*tokens?\)|'
            r'(?:Churn|Work|Cogitat|Contemplat|Cerebrat|Levitat|Medit|Ponder|Idealiz|Ruminat)\w*'
            r'\s+(?:for\s*)?\d+\s*(?:seconds?|s\b)|'
            r'Thinking\.{0,3}|Processing\.{0,3}|Working\.{0,3}).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC session status and thinking messages'
    },

    # 7. CC Permission Prompts
    {
        'name': 'cc_permission_prompts',
        'pattern': re.compile(
            r'^(?:Allow|Approve|Press Y|Do you want to).*(?:y/n|\[Y/n\]|\[y/N\]).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC permission/approval prompts'
    },

    # 8. CC Spinner Characters
    {
        'name': 'cc_spinner_chars',
        'pattern': re.compile(r'^[✻✽✓✗⏵✶▘⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*$', re.MULTILINE),
        'replacement': '',
        'description': 'CC spinner/status indicator characters'
    },

    # 9. CC Hook Messages
    {
        'name': 'cc_hook_messages',
        'pattern': re.compile(
            r'^(?:(?:Ran|Read)\s*\d+\s*(?:hook|file|tool)|'
            r'\d+\s*(?:stop|start)?\s*hooks?|hook error).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC hook execution messages'
    },

    # 10. CC Feedback Prompts
    {
        'name': 'cc_feedback_prompts',
        'pattern': re.compile(
            r'^(?:how is claude doing|'
            r'\d:\s*(?:bad|fine|good|dismiss)|'
            r'1:\s*bad.*2:\s*fine.*3:\s*good).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC feedback rating prompts'
    },

    # 11. CC Keyboard Hints
    {
        'name': 'cc_keyboard_hints',
        'pattern': re.compile(
            r'(?:ctrl[+-]|shift[+-]tab|\? for shortcuts|escape to cancel)',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC keyboard shortcut hints'
    },

    # 12. CC Model/Version Lines
    {
        'name': 'cc_model_lines',
        'pattern': re.compile(
            r'^(?:claude code v|claude\.ai|anthropic|'
            r'(?:opus|sonnet|haiku)\s*[-:]|'
            r'~\/\w+\s*$).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'CC model and version information'
    },

    # 13. Context Injection Artifacts
    {
        'name': 'context_artifacts',
        'pattern': re.compile(
            r'^(?:Read context(?:_[a-zA-Z0-9]+)?\.md(?: and respond)?|Current Message|Memory Context|Recent Conversation):?\s*$|'
            r'^---+\s*$|'
            r'^respond to (?:the )?user|latest message',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Context injection markers and separators'
    },

    # 13b. Router Instruction Echo (Claude echoing the instruction prompt)
    # This is the #1 source of leakage - catches "Current Message section." at start of messages
    {
        'name': 'instruction_echo',
        'pattern': re.compile(
            r'^(?:Current Message section|Message section|in the Current Message section)\.?\s*(?:\n|$)',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Claude echoing router instruction text'
    },

    # 13c. Answer prefix after instruction echo (catches "Answer: " at line start)
    {
        'name': 'answer_prefix',
        'pattern': re.compile(
            r'^Answer:\s*',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Answer: prefix from instruction following'
    },

    # 14. Prompt Markers (standalone or with commands)
    {
        'name': 'prompt_markers',
        'pattern': re.compile(r'^[>❯]\s*.*$', re.MULTILINE),
        'replacement': '',
        'description': 'Prompt markers and lines starting with them'
    },

    # 14a. Slash commands that leak (e.g., /clear sent by scheduler)
    {
        'name': 'leaked_slash_commands',
        'pattern': re.compile(r'^/(?:clear|help|quit|exit|reset|compact)\s*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Leaked slash commands from scheduler/router'
    },

    # 14b. Task Output IDs
    {
        'name': 'task_output_ids',
        'pattern': re.compile(r'^Task Output\s+[a-z0-9]+\s*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Internal task output ID markers'
    },

    # 14c. Background command errors
    {
        'name': 'background_cmd_errors',
        'pattern': re.compile(r'^Background command.*(?:failed|exit code).*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Background command error messages'
    },

    # 14d. Bypass permissions status line
    {
        'name': 'bypass_permissions_line',
        'pattern': re.compile(r'^.*bypass permissions.*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Bypass permissions status line'
    },

    # 14e. Lone JSON brackets
    {
        'name': 'lone_json_brackets',
        'pattern': re.compile(r'^[\{\}]\s*$', re.MULTILINE),
        'replacement': '',
        'description': 'Standalone JSON brackets'
    },

    # 15. Nested Output Markers (with optional leading whitespace)
    {
        'name': 'nested_markers',
        'pattern': re.compile(r'^\s*⎿.*$', re.MULTILINE),
        'replacement': '',
        'description': 'CC nested output markers'
    },

    # 16. Excessive Blank Lines (normalise to max 2)
    {
        'name': 'excess_blank_lines',
        'pattern': re.compile(r'\n{3,}'),
        'replacement': '\n\n',
        'description': 'More than 2 consecutive newlines'
    },

    # 17. Leading/Trailing Whitespace (MUST be last)
    {
        'name': 'trim_whitespace',
        'pattern': re.compile(r'^\s+|\s+$'),
        'replacement': '',
        'description': 'Leading and trailing whitespace'
    },
]


# Additional patterns for aggressive cleaning
AGGRESSIVE_PATTERNS = [
    # JSON field leakage (expanded to catch nutrition API fields)
    {
        'name': 'json_field_leakage',
        'pattern': re.compile(
            r'^"?(?:query|count|id|url|limit|offset|page|size|total|meal_type|'
            r'description|calories|protein|carbs|fat|breakfast|lunch|dinner|snack)"?\s*[:=].*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Leaked JSON field lines'
    },

    # Partial JSON structures (colon-prefixed values, brackets)
    {
        'name': 'json_fragments',
        'pattern': re.compile(
            r'^[:\{]\s*"?\w+"?\s*[:,].*$|'  # Lines starting with : or { followed by key
            r'^"[a-z_]+"\s*:\s*"[^"]*"[,}]?\s*$',  # "key": "value" lines
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Partial JSON structure fragments'
    },

    # Curl commands
    {
        'name': 'curl_commands',
        'pattern': re.compile(r'^.*curl\s+-?s?\s+.*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Curl command lines'
    },

    # URL-encoded fragments (expanded to catch nutrition API params)
    {
        'name': 'url_encoded_fragments',
        'pattern': re.compile(
            r'^[a-z_]+=\d+[gG]?\+.*$|'  # param=50g+something
            r'^[a-z]+\+[a-z]+\+.*$|'  # word+word+word (URL encoded spaces)
            r'^[a-z_]+=[A-Za-z0-9,+%&]+$|'  # key=value with URL chars
            r'^\w+\+\w+\+\w+.*(?:\+|,|%).*$',  # Multiple + separated words
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'URL-encoded parameter fragments'
    },

    # API endpoint fragments
    {
        'name': 'api_endpoint_fragments',
        'pattern': re.compile(
            r'^.*(?:localhost|127\.0\.0\.1|172\.\d+\.\d+\.\d+):\d+/.*$|'  # localhost URLs
            r'^/(?:nutrition|api|gmail|calendar)/\w+.*$',  # API paths
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'API endpoint URL fragments'
    },

    # External API URLs (Open-Meteo, etc.)
    {
        'name': 'external_api_urls',
        'pattern': re.compile(
            r'^"?https?://(?:api\.|www\.)?(?:open-meteo|openweathermap|weatherapi|'
            r'api\.weather|maps\.googleapis|nominatim)\.(?:com|org|io)/[^\s"]*"?\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'External API URL leakage'
    },

    # Generic API-looking URLs with query params
    {
        'name': 'api_query_urls',
        'pattern': re.compile(
            r'^"?https?://[^\s"]+\?(?:latitude|longitude|lat|lon|key|apikey|'
            r'appid|q=|query=|location=)[^\s"]*"?\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'URLs with API query parameters'
    },

    # Diff markers with line numbers
    {
        'name': 'diff_markers',
        'pattern': re.compile(r'^\d+\s*[-+]\s*(?:from|import|def|class|if|for|while|return).*$', re.MULTILINE),
        'replacement': '',
        'description': 'Code diff lines'
    },

    # Edit tool unchanged lines
    {
        'name': 'unchanged_lines',
        'pattern': re.compile(r'^\d+\s+unchanged\s+line.*$', re.MULTILINE | re.IGNORECASE),
        'replacement': '',
        'description': 'Edit tool unchanged line markers'
    },

    # Weather JSON fragments (Open-Meteo API leakage)
    {
        'name': 'weather_json_fragments',
        'pattern': re.compile(
            r',?"(?:precipitation|precipitation_prob|wind_speed|wind_gust|condition|icon|'
            r'temp|temp_min|temp_max|temperature|feels_like|temperature_2m|'
            r'humidity|pressure|cloud|cloud_cover|uv|uv_index|visibility|'
            r'rain_probability|rain_chance|weather_code|sunrise|sunset|'
            r'precipitation_probability)":\s*'
            r'(?:\d+\.?\d*|"[^"]*"|\[[^\]]*\])[,}]?',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Leaked weather JSON data'
    },

    # Open-Meteo API metadata JSON fragments
    {
        'name': 'open_meteo_metadata',
        'pattern': re.compile(
            r',?"(?:utc_offset_seconds|timezone_abbreviation|timezone|elevation|'
            r'latitude|longitude|generationtime_ms|hourly_units|hourly|daily_units|daily)":\s*'
            r'(?:\d+\.?\d*|"[^"]*"|\{[^}]*\})[,}]?',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Open-Meteo API metadata leakage'
    },

    # Weather API URL query parameter fragments
    {
        'name': 'weather_url_params',
        'pattern': re.compile(
            r'(?:^|\s)(?:hourly|daily|latitude|longitude|timezone|'
            r'current_weather|forecast_days|past_days)='
            r'[a-zA-Z0-9_,.-]+(?:&[a-zA-Z0-9_=,.-]+)*'
            r'(?:\.\.\.)?\)?',  # Also match trailing ...) from truncation
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Weather API URL query parameters'
    },

    # Truncated JSON key-value pairs (e.g., "precipitation_prob":"icon)
    {
        'name': 'truncated_json_pairs',
        'pattern': re.compile(
            r',?"[a-z_]+":\s*"[a-z_]*$',  # JSON key with incomplete string value
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Truncated JSON key-value pairs'
    },

    # Orphan brackets/parentheses from truncated content
    {
        'name': 'orphan_brackets',
        'pattern': re.compile(
            r'^[\)\]\}]+\s*$|'  # Lines that are just closing brackets
            r'^\s*[\(\[\{]+\s*$',  # Lines that are just opening brackets
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Orphaned brackets from truncated API content'
    },
    # Catch-all for remaining JSON-like fragments with leading comma
    {
        'name': 'json_comma_fragments',
        'pattern': re.compile(
            r'^,?"[a-z_]+":\s*(?:\d+\.?\d*|"[^"]*")[,}]?\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Generic JSON key:value fragments'
    },

    # ISO timestamp fragments (e.g., T15:11:15.596187+00:00"})
    {
        'name': 'iso_timestamp_fragments',
        'pattern': re.compile(
            r'^T?\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?["\}\]]*\s*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Orphaned ISO timestamp fragments'
    },

    # JSON datetime strings that got split (date part or time part alone)
    {
        'name': 'split_datetime_fragments',
        'pattern': re.compile(
            r'^"?\d{4}-\d{2}-\d{2}[T\s]?$|'  # Date part alone
            r'^[T\s]?\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"?\}?\s*$',  # Time part alone
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Split datetime string fragments'
    },

    # Mid-text JSON fragments (numbers followed by JSON like "60595703,\"utc...")
    # Also catches trailing large numbers after cleanup (API generation times, etc.)
    {
        'name': 'mid_text_json',
        'pattern': re.compile(
            r'\d{5,}[,\s]*"[a-z_]+":\s*(?:\d+\.?\d*|"[^"]*")|'  # Number before JSON
            r'(?:^|\s)\d{6,}\s*(?=\n|$)',  # Trailing large numbers on own line (lookahead, don't consume next)
            re.IGNORECASE | re.MULTILINE
        ),
        'replacement': ' ',
        'description': 'Numeric IDs followed by JSON fragments'
    },

    # Partial API response fragments with coordinates/timezone
    {
        'name': 'api_response_fragments',
        'pattern': re.compile(
            r'["\']?(?:GMT|UTC|Europe/\w+|America/\w+|Asia/\w+)["\']?'
            r'[,\s]*["\']?(?:timezone_abbreviation|timezone|elevation)["\']?\s*[:=]',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Partial API response with timezone/location data'
    },

    # Standalone coordinate-like numbers (latitude/longitude/elevation patterns)
    {
        'name': 'coordinate_numbers',
        'pattern': re.compile(
            r'(?:^|\s)[-]?\d{1,3}\.\d{4,}(?:,|\s*")',  # 51.509865," or similar
            re.MULTILINE
        ),
        'replacement': ' ',
        'description': 'Standalone coordinate numbers'
    },

    # Internal file paths (Claude Code project/cache paths)
    {
        'name': 'internal_file_paths',
        'pattern': re.compile(
            r'^(?:/home|/mnt|C:\\|/tmp|~)/.*?(?:\.claude|peterbot|projects)/.*$|'
            r'.*\.(?:jsonl|cache|tmp|log)\s*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Internal file paths from Claude Code'
    },

    # Claude Code status lines with timing/token info
    {
        'name': 'status_with_timing',
        'pattern': re.compile(
            r'^[✻✽⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*(?:Sketching|Thinking|Working|Processing|Pondering|Reading|Writing).*?'
            r'(?:\d+s|\d+\.\d+s|↓|↑|\d+k?\s*tokens?).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Status lines with timing and token info'
    },

    # Double-pipe and command chain fragments
    {
        'name': 'command_chain_fragments',
        'pattern': re.compile(
            r'^\s*(?:\|\||&&|;)\s*(?:echo|curl|grep|sed|awk|cat|head|tail|sort|wc|true|false).*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Command chain fragments (|| echo, && curl, etc.)'
    },

    # Claude Code explorer/project references
    {
        'name': 'claude_code_refs',
        'pattern': re.compile(
            r'\.claude/projects/|\.claude/settings|'
            r'/home/\w+/\.claude/|'
            r'peterbot/\*\.jsonl',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Claude Code project and settings references'
    },

    # Truncated curl command fragments with API paths
    {
        'name': 'curl_api_fragments',
        'pattern': re.compile(
            r'^.*(?:pi/|api/|hb/)(?:inventory|orders|tasks|listings?)/[a-f0-9-]+.*$|'
            r'^[a-f0-9]{3,}-[a-f0-9-]+"?\s*\\?\s*$|'  # Partial UUID like "7e5-f80cb411cefd" \
            r'^[a-f0-9-]{20,}"?\s*\\?\s*$',  # Full UUID fragments
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Truncated curl commands with API paths and UUIDs'
    },

    # Backslash line continuations from curl/shell commands
    {
        'name': 'line_continuations',
        'pattern': re.compile(
            r'^[^a-zA-Z]*"\s*\\$|'  # Lines ending with " \
            r'^\s*\\$|'  # Lines that are just \
            r'^["\']?https?://[^\s]+\s*\\$',  # URLs with trailing \
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Shell line continuations'
    },

    # Partial API endpoint paths (truncated)
    {
        'name': 'partial_api_paths',
        'pattern': re.compile(
            r'^(?:pi|hb|api)/\w+/[a-f0-9-]+',  # pi/inventory/uuid
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Partial API paths from truncated commands'
    },

    # API response JSON fields (message_id, event_id, session_id, etc.)
    {
        'name': 'api_json_fields',
        'pattern': re.compile(
            r'^"(?:message_id|event_id|session_id|deleted_id|purchase_id|item_id|'
            r'task_id|user_id|order_id|set_number|sku|asin)":\s*"[^"]*"[,}]?\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Leaked API response JSON ID fields'
    },

    # JSON key:number patterns (e.g., "cost": 0, "quantity": 1)
    {
        'name': 'json_key_number',
        'pattern': re.compile(
            r',?\s*"(?:cost|quantity|count|total|price|amount|calories|protein|carbs|fat|'
            r'limit|offset|page|size)":\s*\d+[,}]?',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'JSON key:number patterns'
    },

    # JSON key:null/bool patterns (e.g., "amazon": null, "available": true)
    {
        'name': 'json_key_null_bool',
        'pattern': re.compile(
            r'^"[a-z_]+":\s*(?:null|true|false)[,}]?\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'JSON key:null/bool patterns'
    },

    # Python one-liner command fragments
    {
        'name': 'python_oneliner',
        'pattern': re.compile(
            r'^"?import\s+(?:sys|json|os|re)[,;].*$|'
            r'^"?python3?\s+-c\s+[\'"].*$|'
            r'^.*json\.load\(sys\.stdin\).*$|'
            r'^\s*d\.get\([\'"].*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Python one-liner command fragments'
    },

    # Inline thinking/spinner status (not at line start)
    {
        'name': 'inline_thinking_status',
        'pattern': re.compile(
            r'[✻✽]\s*(?:Sketching|Thinking|Working|Concocting|Pondering)[✻✽]?\s*'
            r'\([^)]*(?:tokens?|thinking|s\s*[✻✽])[^)]*\)',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Inline thinking status with spinners'
    },

    # Plain thinking status without spinner (e.g., "Concocting (thought for 2s)")
    {
        'name': 'plain_thinking_status',
        'pattern': re.compile(
            r'^[✻✽]?\s*(?:Sketching|Thinking|Working|Concocting|Pondering|Processing)\s*'
            r'\([^)]*(?:\d+s|thought|tokens?)[^)]*\)\s*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Plain thinking status lines'
    },

    # Standalone spinner characters at line start
    {
        'name': 'standalone_spinner',
        'pattern': re.compile(
            r'^[✻✽⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s+\w+',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Standalone spinner at line start'
    },

    # Token count arrows (↓ ↑) with numbers
    {
        'name': 'token_arrows',
        'pattern': re.compile(
            r'[↓↑]\s*\d+\.?\d*k?\s*tokens?',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Token count arrows'
    },

    # Curl with Content-Type header fragments
    {
        'name': 'curl_content_type',
        'pattern': re.compile(
            r'^.*(?:application/json|Content-Type:).*-d\s*[\'"].*$|'
            r'^.*-H\s*[\'"]Content-Type:.*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Curl commands with Content-Type headers'
    },

    # Endpoint discovery/listing output
    {
        'name': 'endpoint_listing',
        'pattern': re.compile(
            r'^.*(?:Endpoint|endpoint)\s+(?:not\s+f|exists|available).*$',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'Endpoint discovery status messages'
    },

    # Bash head/tail/grep command references (including in pipes)
    {
        'name': 'bash_pipe_refs',
        'pattern': re.compile(
            r'^\s*(?:\|\s*)?(?:head|tail|grep|sed|awk|sort|wc)\s+-?\d*\s*\)?$|'
            r'\|\s*(?:head|tail)\s+-\d+\)?',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Truncated bash pipe commands'
    },

    # OAuth/API error fragments
    {
        'name': 'api_error_fragments',
        'pattern': re.compile(
            r"^.*(?:invalid_scope|Unauthorized|'error':|'error_description':).*$",
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'API error fragments'
    },

    # Curl -H header flags
    {
        'name': 'curl_header_flag',
        'pattern': re.compile(
            r'^.*-H\s*["\'][^"\']*["\'].*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Curl -H header flag lines'
    },

    # Curl -d data flags
    {
        'name': 'curl_data_flag',
        'pattern': re.compile(
            r"^.*-d\s*'?\{[^}]*$|"
            r"^.*-d\s*'[^']*'\s*$",
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Curl -d data flag lines'
    },

    # API paths without UUID (hb/inventory/status, pi/orders/list)
    {
        'name': 'api_path_no_uuid',
        'pattern': re.compile(
            r'^(?:pi|hb|api)/\w+/\w+\s*$|'
            r'/(?:pi|hb|api)/\w+/\w+',
            re.MULTILINE | re.IGNORECASE
        ),
        'replacement': '',
        'description': 'API paths without UUID'
    },

    # URL query parameters
    {
        'name': 'url_query_params',
        'pattern': re.compile(
            r'/[a-z-]+\?[a-z_]+=\S+',
            re.IGNORECASE
        ),
        'replacement': '',
        'description': 'URLs with query parameters'
    },

    # Python tracebacks
    {
        'name': 'python_traceback',
        'pattern': re.compile(
            r'^Traceback \(most recent.*$|'
            r'^\s*File "[^"]+", line \d+.*$',
            re.MULTILINE
        ),
        'replacement': '',
        'description': 'Python traceback lines'
    },
]


def sanitise(
    raw_text: str,
    bypass: bool = False,
    aggressive: bool = True,
    track_rules: bool = False
) -> SanitiserResult | str:
    """Sanitise Claude Code output for Discord.

    Args:
        raw_text: Raw CC output text
        bypass: If True, wrap raw output in code block (--raw mode)
        aggressive: If True, apply additional cleaning patterns
        track_rules: If True, return SanitiserResult with metadata

    Returns:
        Cleaned text string, or SanitiserResult if track_rules=True
    """
    if not raw_text:
        return SanitiserResult('', [], 0, 0) if track_rules else ''

    original_length = len(raw_text)
    rules_applied = []

    # --raw / --debug bypass mode
    if bypass:
        result = f"```\n{raw_text}\n```"
        if track_rules:
            return SanitiserResult(result, ['bypass'], original_length, len(result))
        return result

    text = raw_text

    # Apply standard rules in order
    for rule in SANITISER_RULES:
        before = text
        text = rule['pattern'].sub(rule['replacement'], text)
        if text != before:
            rules_applied.append(rule['name'])

    # Apply aggressive patterns if enabled
    if aggressive:
        for rule in AGGRESSIVE_PATTERNS:
            before = text
            text = rule['pattern'].sub(rule['replacement'], text)
            if text != before:
                rules_applied.append(f"aggressive:{rule['name']}")

    # Normalise mid-sentence line breaks (common in Claude Code output)
    # Pattern: lowercase letter or comma/semicolon followed by newline then lowercase
    # This fixes "berries\nfor" -> "berries for"
    before = text
    text = re.sub(r'([a-z,;:])\n([a-z])', r'\1 \2', text)
    if text != before:
        rules_applied.append('mid_sentence_linebreaks')

    # Also fix double-newlines that break sentences mid-flow
    # Pattern: word ending in comma/lowercase followed by \n\n then lowercase word
    before = text
    text = re.sub(r'([a-z,])\n\n([a-z])', r'\1 \2', text)
    if text != before:
        rules_applied.append('mid_paragraph_breaks')

    # Collapse extra spacing between list items (prefer tight lists)
    # Pattern: list item followed by blank line(s) followed by another list item
    # Apply repeatedly until no more changes (handles long lists)
    list_pattern = re.compile(r'(^[-*•]\s+.+$)\n\n+([-*•]\s+)', re.MULTILINE)
    list_changed = False
    while True:
        before = text
        text = list_pattern.sub(r'\1\n\2', text)
        if text == before:
            break
        list_changed = True
    if list_changed:
        rules_applied.append('list_item_spacing')

    # Final cleanup - collapse any remaining multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if track_rules:
        return SanitiserResult(text, rules_applied, original_length, len(text))
    return text


def check_bypass_flag(user_message: str) -> bool:
    """Check if user message contains --raw or --debug flag."""
    if not user_message:
        return False
    return bool(re.search(r'--(?:raw|debug)\b', user_message, re.IGNORECASE))


def contains_cc_artifacts(text: str) -> bool:
    """Check if text contains any CC artifacts (for validation)."""
    # Quick checks for common artifacts
    artifact_indicators = [
        r'[⏺●⎿├└⏵]',  # CC markers
        r'\x1b\[',  # ANSI codes
        r'Total tokens',  # Token counts
        r'[╭╮╰╯│─]',  # Box drawing
        r'Thinking\.\.\.',  # Status messages
    ]

    for pattern in artifact_indicators:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# =============================================================================
# TESTING UTILITIES
# =============================================================================

def test_sanitiser():
    """Run basic sanitiser tests."""
    test_cases = [
        # Test ANSI codes
        (
            '\x1b[32mgreen text\x1b[0m normal',
            'green text normal'
        ),
        # Test CC bullets
        (
            '⏺ First point\n⏺ Second point',
            'First point\nSecond point'
        ),
        # Test token counts
        (
            'Here is the answer.\n\nTotal tokens: 1,247 | Cost: $0.003',
            'Here is the answer.'
        ),
        # Test session headers
        (
            '╭────────────────────╮\n│ Session info       │\n╰────────────────────╯\n\nActual content',
            'Actual content'
        ),
        # Test tool indicators
        (
            '⎿ Read file.txt\n\nThe file contains data.',
            'The file contains data.'
        ),
        # Test thinking status
        (
            'Thinking for 5 seconds...\n\nHere is my answer.',
            'Here is my answer.'
        ),
        # Test excessive blank lines
        (
            'First paragraph.\n\n\n\n\nSecond paragraph.',
            'First paragraph.\n\nSecond paragraph.'
        ),
        # Test --raw bypass
        (
            '⏺ Raw content with artifacts',
            '```\n⏺ Raw content with artifacts\n```',
            True  # bypass=True
        ),
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        if len(test) == 3:
            input_text, expected, bypass = test
        else:
            input_text, expected = test
            bypass = False

        result = sanitise(input_text, bypass=bypass)

        if result == expected:
            passed += 1
            print(f"✓ PASS")
        else:
            failed += 1
            print(f"✗ FAIL")
            print(f"  Input: {repr(input_text[:50])}")
            print(f"  Expected: {repr(expected[:50])}")
            print(f"  Got: {repr(result[:50])}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_sanitiser()
