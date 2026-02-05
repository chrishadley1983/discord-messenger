"""Run parser regression test and write output to file."""

import sys
sys.path.insert(0, '.')

import json
from pathlib import Path

from domains.peterbot.parser_regression import RegressionRunner

def main():
    output_file = Path("data/regression_report.txt")
    json_file = Path("data/regression_report.json")

    runner = RegressionRunner()
    report = runner.run()

    # Write text report
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report.summary())

    # Write JSON report
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)

    print(f"Text report written to: {output_file}")
    print(f"JSON report written to: {json_file}")
    print(f"Pass rate: {report.passed}/{report.total} ({report.pass_rate:.1%})")
    print(f"Regressions: {report.regressions}")
    print(f"Improvements: {report.improvements}")


if __name__ == "__main__":
    main()
