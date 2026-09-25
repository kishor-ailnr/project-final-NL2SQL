"""
run_tests.py
------------
Cross-platform test runner for local development and CI pipelines.
Automatically inspects GEMINI_API_KEY:
  - If present: runs the complete test suite (unit + Gemini integration tests).
  - If absent: runs unit tests only (-m 'not integration'), preventing CI failures
    when API credentials are not yet configured in GitHub Secrets.
"""

import os
import sys
import subprocess

def main():
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    args = [
        sys.executable,
        "-m",
        "pytest",
        "-v",
    ]

    # Check if pytest-cov is available
    try:
        import pytest_cov
        args.extend(["--cov=app", "--cov-report=term-missing"])
    except ImportError:
        print("Notice: pytest-cov not installed, proceeding without coverage flag.")

    if not gemini_key:
        print("\n" + "=" * 70)
        print("  GEMINI_API_KEY not detected in environment.")
        print("  Running unit tests only (skipping @pytest.mark.integration)...")
        print("=" * 70 + "\n")
        args.extend(["-m", "not integration"])
    else:
        print("\n" + "=" * 70)
        print("  GEMINI_API_KEY detected.")
        print("  Running complete test suite (unit + integration)...")
        print("=" * 70 + "\n")

    print(f"Executing: {' '.join(args)}\n")
    proc = subprocess.run(args)
    sys.exit(proc.returncode)

if __name__ == "__main__":
    main()
