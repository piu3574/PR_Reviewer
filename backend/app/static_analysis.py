import subprocess
import json
import tempfile
import os


def run_pylint(code: str, filename: str = "temp_file.py"):
    """
    Runs pylint on a string of Python code by writing it to a temp file.
    Returns a list of structured issues.
    """
    issues = []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["pylint", tmp_path, "--output-format=json"],
            capture_output=True,
            text=True
        )
        if result.stdout:
            raw_issues = json.loads(result.stdout)
            for item in raw_issues:
                issues.append({
                    "file_name": filename,
                    "line_number": item.get("line"),
                    "issue_type": item.get("symbol", "style"),
                    "severity": map_pylint_severity(item.get("type")),
                    "source": "static",
                    "description": item.get("message")
                })
    finally:
        os.remove(tmp_path)

    return issues


def map_pylint_severity(pylint_type: str) -> str:
    mapping = {
        "error": "high",
        "warning": "medium",
        "convention": "low",
        "refactor": "low"
    }
    return mapping.get(pylint_type, "low")


def run_bandit(code: str, filename: str = "temp_file.py"):
    """
    Runs bandit (security scanner) on a string of Python code.
    Returns a list of structured issues.
    """
    issues = []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["bandit", "-f", "json", tmp_path],
            capture_output=True,
            text=True
        )
        if result.stdout:
            raw = json.loads(result.stdout)
            for item in raw.get("results", []):
                issues.append({
                    "file_name": filename,
                    "line_number": item.get("line_number"),
                    "issue_type": item.get("test_id", "security"),
                    "severity": item.get("issue_severity", "medium").lower(),
                    "source": "static",
                    "description": item.get("issue_text")
                })
    finally:
        os.remove(tmp_path)

    return issues


def analyze_python_file(code: str, filename: str = "temp_file.py"):
    """
    Runs both pylint and bandit on a Python file's content.
    Returns a combined list of issues.
    """
    all_issues = []
    all_issues.extend(run_pylint(code, filename))
    all_issues.extend(run_bandit(code, filename))
    return all_issues

def run_eslint(code: str, filename: str = "temp_file.js"):
    """
    Runs eslint on a string of JavaScript code by writing it to a temp file
    INSIDE the backend folder, so eslint.config.js is discovered correctly.
    """
    issues = []

    # Create temp file inside backend/ instead of system temp dir
    tmp_dir = os.path.dirname(os.path.abspath(__file__))  # backend/app
    tmp_dir = os.path.join(tmp_dir, "..")  # go up to backend/
    tmp_path = os.path.join(tmp_dir, "_eslint_temp.js")

    with open(tmp_path, "w") as tmp:
        tmp.write(code)

    try:
        result = subprocess.run(
            ["npx", "eslint", tmp_path, "--format=json"],
            capture_output=True,
            text=True,
            shell=True,
            cwd=tmp_dir  # run eslint from backend/ so it finds eslint.config.js
        )
        if result.stdout:
            raw_results = json.loads(result.stdout)
            for file_result in raw_results:
                for msg in file_result.get("messages", []):
                    issues.append({
                        "file_name": filename,
                        "line_number": msg.get("line"),
                        "issue_type": msg.get("ruleId") or "syntax-error",
                        "severity": map_eslint_severity(msg.get("severity")),
                        "source": "static",
                        "description": msg.get("message")
                    })
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return issues


def map_eslint_severity(eslint_severity: int) -> str:
    # eslint severity: 1 = warning, 2 = error
    mapping = {
        1: "medium",
        2: "high"
    }
    return mapping.get(eslint_severity, "low")


def analyze_js_file(code: str, filename: str = "temp_file.js"):
    """
    Runs eslint on a JavaScript file's content.
    """
    return run_eslint(code, filename)