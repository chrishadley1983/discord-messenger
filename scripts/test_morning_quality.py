"""Test the morning quality report generator."""

import sys
sys.path.insert(0, '.')

import asyncio
from pathlib import Path

from domains.peterbot.morning_quality_report import MorningQualityReportBuilder

def main():
    output_file = Path("data/morning_quality_report.txt")

    builder = MorningQualityReportBuilder()
    report = builder.build()

    # Write the report
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report.format_discord())

    print(f"Morning quality report written to: {output_file}")
    print(f"\nPreview (first 40 lines):")
    print("-" * 50)
    lines = report.format_discord().split('\n')
    for line in lines[:40]:
        print(line)
    if len(lines) > 40:
        print(f"... ({len(lines) - 40} more lines)")


if __name__ == "__main__":
    main()
