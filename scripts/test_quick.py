#!/usr/bin/env python3
"""
Quick test runner.

Usage:
    python scripts/test_quick.py              # Run all tests
    python scripts/test_quick.py --verbose    # Run with verbose output
    python scripts/test_quick.py --coverage   # Run with coverage report
    python scripts/test_quick.py test_errors  # Run specific test file
"""

import sys
import subprocess


def main():
    """Run pytest."""

    cmd = [sys.executable, "-m", "pytest"]

    cmd.extend([
        "--tb=short",
        "--color=yes",
    ])

    if "--verbose" in sys.argv or "-v" in sys.argv:
        cmd.append("-v")
        sys.argv = [arg for arg in sys.argv if arg not in ["--verbose", "-v"]]

    if "--coverage" in sys.argv:
        cmd.extend([
            "--cov=server",
            "--cov-report=term-missing",
            "--cov-report=html"
        ])
        sys.argv.remove("--coverage")

    # Add any remaining arguments (like specific test files)
    if len(sys.argv) > 1:
        test_target = sys.argv[1]
        if not test_target.startswith("-"):
            if not test_target.startswith("tests/"):
                test_target = f"tests/{test_target}"
            if not test_target.endswith(".py"):
                test_target = f"{test_target}.py"
            cmd.append(test_target)
    else:
        cmd.append("tests/")

    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
