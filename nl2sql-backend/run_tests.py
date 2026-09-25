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

    print(f"Python: {sys.executable} ({sys.version.splitlines()[0]})", flush=True)
    print(f"Working Directory: {os.getcwd()}", flush=True)

    args = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        "-v",
    ]

    try:
        import pytest_cov
        args.extend(["--cov=app", "--cov-report=term-missing"])
    except ImportError:
        print("Notice: pytest-cov not installed, proceeding without coverage flag.", flush=True)

    if not gemini_key:
        print("GEMINI_API_KEY not detected in environment. Running unit tests only.", flush=True)
        args.extend(["-m", "not integration"])
    else:
        print("GEMINI_API_KEY detected. Running full test suite.", flush=True)

    print(f"Executing: {' '.join(args)}\n", flush=True)
    proc = subprocess.run(args, capture_output=True, text=True)

    print("=== PYTEST STDOUT ===", flush=True)
    print(proc.stdout, flush=True)
    if proc.stderr:
        print("=== PYTEST STDERR ===", flush=True)
        print(proc.stderr, flush=True)
    print(f"=== PYTEST EXIT CODE: {proc.returncode} ===", flush=True)

    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(f"### Pytest Run Results\n- **Command:** `{' '.join(args)}`\n- **Exit Code:** {proc.returncode}\n\n```text\n")
                f.write(proc.stdout[-3000:] if len(proc.stdout) > 3000 else proc.stdout)
                if proc.stderr:
                    f.write("\nSTDERR:\n" + proc.stderr)
                f.write("\n```\n")
        except Exception as e:
            print(f"Notice: Failed to write to GITHUB_STEP_SUMMARY: {e}", flush=True)

    sys.exit(proc.returncode)

if __name__ == "__main__":
    main()
