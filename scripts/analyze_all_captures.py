"""Analyze ALL captures to identify leak patterns for regression testing."""

import sqlite3
import re
from pathlib import Path
from collections import Counter

db_path = Path('data/parser_fixtures.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get ALL captures
captures = conn.execute('''
    SELECT id, captured_at, screen_before, screen_after, parser_output, pipeline_output,
           was_empty, had_ansi, had_echo, user_reacted, skill_name
    FROM captures
    ORDER BY captured_at DESC
''').fetchall()

print(f'=== ANALYZING {len(captures)} TOTAL CAPTURES ===')
print()

# Comprehensive pattern detection
patterns_found = Counter()
samples_by_pattern = {}

leak_patterns = {
    # Instruction/Context
    'instruction_current_msg': (r'Current Message section', 'Instruction echo'),
    'instruction_message_section': (r'^Message section\.', 'Message section echo'),
    'instruction_answer': (r'^Answer:', 'Answer prefix'),
    'context_memory': (r'Memory Context|Relevant Knowledge', 'Memory context marker'),
    'context_recent': (r'Recent Conversation', 'Recent conversation marker'),

    # JSON structures
    'json_message_id': (r'"message_id":', 'JSON message_id'),
    'json_event_id': (r'"event_id":', 'JSON event_id'),
    'json_session_id': (r'"session_id":', 'JSON session_id'),
    'json_deleted_id': (r'"deleted_id":', 'JSON deleted_id'),
    'json_set_number': (r'"set_number":', 'JSON set_number'),
    'json_generic_id': (r'"[a-z]+_id":', 'JSON generic ID field'),
    'json_key_string': (r'"[a-z_]+"\s*:\s*"[^"]*"', 'JSON key:string'),
    'json_key_number': (r'"[a-z_]+"\s*:\s*\d+', 'JSON key:number'),
    'json_key_bool': (r'"[a-z_]+"\s*:\s*(?:true|false|null)', 'JSON key:bool/null'),
    'json_open_brace': (r'^\s*\{\s*$', 'Standalone {'),
    'json_close_brace': (r'^\s*\}\s*$', 'Standalone }'),
    'json_open_bracket': (r'^\s*\[\s*$', 'Standalone ['),
    'json_close_bracket': (r'^\s*\]\s*$', 'Standalone ]'),

    # Claude Code UI
    'cc_spinner_braille': (r'[\u2817\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f]', 'Braille spinner'),
    'cc_spinner_star': (r'[\u273b\u273d]', 'Star spinner'),
    'cc_thinking_time': (r'(?:Sketching|Thinking|Working|Concocting|Pondering|Processing).*\d+s', 'Thinking with time'),
    'cc_thinking_plain': (r'(?:Sketching|Thinking|Working|Concocting|Pondering)\s*\(', 'Thinking status'),
    'cc_tokens_count': (r'\d+\.?\d*k?\s*tokens', 'Token count'),
    'cc_token_arrow_down': (r'\u2193\s*\d+', 'Down arrow tokens'),
    'cc_token_arrow_up': (r'\u2191\s*\d+', 'Up arrow tokens'),
    'cc_tool_marker': (r'[\u23bf\u251c\u2514\u23f5]\s*(?:Read|Write|Edit|Bash|Glob|Grep|WebSearch|WebFetch)', 'Tool marker'),
    'cc_bullet': (r'^[\u23fa\u25cf]\s*', 'CC bullet'),
    'cc_box_drawing': (r'[\u256d\u256e\u2570\u256f\u2502\u2500\u250c\u2510\u2514\u2518]', 'Box drawing'),
    'cc_nested_marker': (r'\u23bf', 'Nested output marker'),

    # Paths
    'path_home_user': (r'/home/\w+/', '/home/user/ path'),
    'path_home_chris': (r'/home/chris_hadley/', '/home/chris_hadley/'),
    'path_claude_dir': (r'\.claude/', '.claude/ path'),
    'path_claude_projects': (r'\.claude/projects/', '.claude/projects/'),
    'path_peterbot': (r'peterbot/', 'peterbot/ path'),
    'path_jsonl': (r'\.jsonl', '.jsonl reference'),
    'path_jsonl_glob': (r'\*\.jsonl', '*.jsonl glob'),
    'path_tmp': (r'/tmp/', '/tmp/ path'),
    'path_mnt': (r'/mnt/', '/mnt/ path'),
    'path_windows_c': (r'C:\\', 'Windows C:\\ path'),

    # Commands
    'cmd_curl_flag': (r'curl\s+-[sSfHX]', 'Curl with flags'),
    'cmd_curl_url': (r'curl\s+["\']?https?://', 'Curl with URL'),
    'cmd_pipe_echo': (r'\|\|\s*echo', 'Pipe echo'),
    'cmd_and_curl': (r'&&\s*curl', 'And curl'),
    'cmd_semicolon': (r';\s*(?:echo|curl|grep)', 'Semicolon chain'),
    'cmd_python_c': (r'python3?\s+-c', 'Python -c'),
    'cmd_import_sys': (r'import\s+sys', 'import sys'),
    'cmd_import_json': (r'import\s+json', 'import json'),
    'cmd_json_load': (r'json\.load\(', 'json.load()'),
    'cmd_head_tail': (r'(?:head|tail)\s+-\d+', 'head/tail command'),
    'cmd_grep_flag': (r'grep\s+-', 'grep with flags'),
    'cmd_line_cont': (r'"\s*\\$', 'Line continuation'),
    'cmd_heredoc': (r"<<'?EOF", 'Heredoc marker'),

    # API/URLs
    'api_localhost': (r'localhost:\d+', 'Localhost URL'),
    'api_127': (r'127\.0\.0\.1:\d+', '127.0.0.1 URL'),
    'api_172': (r'172\.\d+\.\d+\.\d+:\d+', '172.x.x.x URL'),
    'api_path_pi': (r'pi/\w+/', 'pi/ API path'),
    'api_path_hb': (r'hb/\w+/', 'hb/ API path'),
    'api_path_api': (r'/api/\w+/', '/api/ path'),
    'api_uuid_full': (r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', 'Full UUID'),
    'api_uuid_partial': (r'[a-f0-9]{4,8}-[a-f0-9]{4}', 'Partial UUID'),
    'api_query_param': (r'\?[a-z_]+=', 'Query parameter'),
    'api_content_type': (r'Content-Type:\s*application/json', 'Content-Type header'),
    'api_header_h': (r'-H\s*["\']', 'Curl -H header'),
    'api_data_d': (r"-d\s*'?\{", 'Curl -d data'),

    # Errors/Status
    'error_unauthorized': (r'Unauthorized', 'Unauthorized error'),
    'error_not_found': (r'(?:Endpoint|Not)\s+(?:not\s+)?found', 'Not found error'),
    'error_invalid_scope': (r'invalid_scope', 'OAuth scope error'),
    'error_invalid_grant': (r'invalid_grant', 'OAuth grant error'),
    'error_traceback': (r'Traceback \(most recent', 'Python traceback'),
    'error_exception': (r'Exception:|Error:', 'Exception/Error'),

    # Weather API specific
    'weather_temp': (r'"temperature[_\w]*":', 'Weather temperature'),
    'weather_precip': (r'"precipitation[_\w]*":', 'Weather precipitation'),
    'weather_coords': (r'"(?:latitude|longitude)":', 'Weather coordinates'),
    'weather_timezone': (r'"timezone[_\w]*":', 'Weather timezone'),

    # Nutrition API specific
    'nutrition_calories': (r'"calories":\s*\d+', 'Nutrition calories'),
    'nutrition_protein': (r'"protein":\s*\d+', 'Nutrition protein'),
    'nutrition_meal_type': (r'"meal_type":', 'Nutrition meal_type'),

    # Misc artifacts
    'artifact_shebang': (r'^#!/', 'Shebang'),
    'artifact_diff_plus': (r'^\+\s*(?:def|class|import|from)', 'Diff + line'),
    'artifact_diff_minus': (r'^-\s*(?:def|class|import|from)', 'Diff - line'),
    'artifact_ansi': (r'\x1b\[', 'ANSI escape'),
    'artifact_task_output': (r'^Task Output\s+[a-z0-9]+', 'Task Output ID'),
    'artifact_bypass_perms': (r'bypass permissions', 'Bypass permissions'),
    'artifact_slash_cmd': (r'^/(?:clear|help|quit|exit|reset)', 'Slash command'),
}

for c in captures:
    output = c['pipeline_output'] or ''

    for pattern_name, (pattern, desc) in leak_patterns.items():
        try:
            if re.search(pattern, output, re.MULTILINE | re.IGNORECASE):
                patterns_found[pattern_name] += 1
                if pattern_name not in samples_by_pattern:
                    # Find the actual match for the sample
                    match = re.search(pattern, output, re.MULTILINE | re.IGNORECASE)
                    if match:
                        start = max(0, match.start() - 20)
                        end = min(len(output), match.end() + 50)
                        samples_by_pattern[pattern_name] = output[start:end].replace('\n', '\\n')
        except Exception as e:
            print(f"Error with pattern {pattern_name}: {e}")

print('=== PATTERN FREQUENCY (sorted by count) ===')
print()
print(f'{"Pattern":<35} | {"Count":>5} | {"Pct":>6} | Description')
print('-' * 80)
for pattern_name, count in patterns_found.most_common():
    desc = leak_patterns[pattern_name][1]
    pct = 100 * count / len(captures)
    print(f'{pattern_name:<35} | {count:>5} | {pct:>5.1f}% | {desc}')

print()
print('=== SAMPLE MATCHES (for test cases) ===')
print()
for pattern_name, count in patterns_found.most_common(30):
    if pattern_name in samples_by_pattern:
        sample = samples_by_pattern[pattern_name][:100]
        # Make safe for console
        safe_sample = sample.encode('ascii', 'replace').decode()
        print(f'{pattern_name}: "{safe_sample}"')

print()
print(f'Total unique pattern types found: {len(patterns_found)}')
total_with_leak = sum(1 for c in captures if c['pipeline_output'] and any(
    re.search(p[0], c['pipeline_output'], re.MULTILINE | re.IGNORECASE)
    for p in leak_patterns.values()
))
print(f'Captures with at least one leak pattern: {total_with_leak}/{len(captures)} ({100*total_with_leak/len(captures):.1f}%)')

# Group by category
print()
print('=== PATTERNS BY CATEGORY ===')
categories = {}
for pattern_name in patterns_found:
    cat = pattern_name.split('_')[0]
    if cat not in categories:
        categories[cat] = 0
    categories[cat] += patterns_found[pattern_name]

for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
    print(f'{cat:<15}: {count:>5} occurrences')

conn.close()
