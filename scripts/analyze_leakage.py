"""Deep dive analysis of Discord message leakage patterns."""

import sqlite3
from pathlib import Path
import re
from datetime import datetime, timedelta

db_path = Path('data/parser_fixtures.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get ALL captures from last 24 hours
captures = conn.execute('''
    SELECT id, captured_at, screen_before, screen_after, parser_output, pipeline_output,
           was_empty, had_ansi, had_echo, user_reacted
    FROM captures
    WHERE captured_at > datetime('now', '-24 hours')
    ORDER BY captured_at DESC
''').fetchall()

print(f'=== DEEP DIVE: {len(captures)} CAPTURES IN LAST 24H ===')
print()

# Comprehensive leak patterns to check
leak_patterns = {
    # Command/shell artifacts
    'cmd_chain': (r'\|\||\&\&|;\s*(?:echo|curl|grep)', 'Command chain (|| && ;)'),
    'curl_fragment': (r'curl\s+-|curl\s+[\'"]', 'Curl command'),
    'line_cont': (r'"\s*\\$', 'Line continuation'),

    # File/path artifacts
    'jsonl_path': (r'\.jsonl', '.jsonl file reference'),
    'claude_path': (r'\.claude/', '.claude/ path'),
    'home_path': (r'/home/\w+/', '/home/user/ path'),
    'project_path': (r'projects?/', 'projects/ path'),

    # API/URL artifacts
    'api_path': (r'(?:api|hb|pi)/\w+/', 'API path fragment'),
    'uuid_fragment': (r'[a-f0-9]{8}-[a-f0-9]{4}|[a-f0-9]{4}-[a-f0-9]{12}', 'UUID fragment'),
    'localhost': (r'localhost:\d+|127\.0\.0\.1:\d+', 'Localhost URL'),
    'http_fragment': (r'https?://[^\s]+\?[^\s]*=', 'URL with query params'),

    # JSON artifacts
    'json_key': (r'"[a-z_]+"\s*:\s*(?:null|true|false|\d+|")', 'JSON key:value'),
    'json_bracket': (r'^\s*[\{\}\[\]]\s*$', 'Standalone JSON bracket'),

    # Claude Code UI artifacts
    'spinner': (r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏✻✽]', 'Spinner character'),
    'thinking': (r'(?:Sketching|Thinking|Working|Processing).*(?:\d+s|tokens)', 'Thinking status'),
    'tool_marker': (r'[⎿├└⏵]\s*(?:Read|Write|Edit|Bash|Glob|Grep)', 'Tool marker'),
    'token_count': (r'\d+\.?\d*k?\s*tokens|↓|↑', 'Token count'),

    # Instruction echo
    'msg_section': (r'Current Message section|Message section', 'Instruction echo'),
    'context_marker': (r'Memory Context|Recent Conversation', 'Context marker'),

    # Code artifacts
    'import_stmt': (r'^import\s+\w+|^from\s+\w+\s+import', 'Import statement'),
    'func_def': (r'^def\s+\w+|^async\s+def', 'Function definition'),
    'python_cmd': (r"python\s+-c\s+['\"]", 'Python -c command'),
}

# Analyze each capture
issues_by_type = {}
all_issues = []

for c in captures:
    output = c['pipeline_output'] or ''
    detected = c['had_echo'] or c['had_ansi']

    issues_found = []
    for pattern_name, (pattern, desc) in leak_patterns.items():
        if re.search(pattern, output, re.MULTILINE | re.IGNORECASE):
            issues_found.append((pattern_name, desc))
            if pattern_name not in issues_by_type:
                issues_by_type[pattern_name] = []
            issues_by_type[pattern_name].append({
                'time': c['captured_at'],
                'detected': detected,
                'preview': output[:200]
            })

    if issues_found:
        all_issues.append({
            'time': c['captured_at'],
            'detected': detected,
            'issues': issues_found,
            'output': output
        })

# Report
print(f'Captures with potential leakage: {len(all_issues)}/{len(captures)}')
print()
print('=== LEAK TYPES FOUND ===')
for pattern_name, occurrences in sorted(issues_by_type.items(), key=lambda x: -len(x[1])):
    detected_count = sum(1 for o in occurrences if o['detected'])
    undetected_count = len(occurrences) - detected_count
    desc = leak_patterns[pattern_name][1]
    status = 'OK' if undetected_count == 0 else f'!! {undetected_count} UNDETECTED'
    print(f'{pattern_name:20} | {len(occurrences):3} occurrences | {status:20} | {desc}')

print()
print('=== UNDETECTED LEAKAGE DETAILS ===')
for issue in all_issues:
    if not issue['detected']:
        undetected_types = [i[0] for i in issue['issues']]
        print(f"\n{issue['time']}")
        print(f"  Types: {', '.join(undetected_types)}")
        # Sanitize for console output
        preview = issue['output'][:300].encode('ascii', 'replace').decode()
        print(f"  Preview: {preview}")

print()
print('=== SAMPLE OUTPUTS FOR EACH LEAK TYPE ===')
for pattern_name, occurrences in sorted(issues_by_type.items(), key=lambda x: -len(x[1]))[:10]:
    undetected = [o for o in occurrences if not o['detected']]
    if undetected:
        print(f"\n--- {pattern_name} ({len(undetected)} undetected) ---")
        sample = undetected[0]
        preview = sample['preview'].encode('ascii', 'replace').decode()
        print(f"  Time: {sample['time']}")
        print(f"  Preview: {preview[:200]}")

conn.close()
