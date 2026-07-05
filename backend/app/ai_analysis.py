import os
import json
import time
from google import genai
from google.genai import errors
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is not set. Check your .env file.")

client = genai.Client(api_key=GOOGLE_API_KEY)

MODEL_NAME = "gemini-2.5-flash"


def build_prompt(filename: str, code: str, static_findings: list) -> str:
    """
    Builds the prompt sent to the AI - includes the code AND
    what static analysis already found, so the AI focuses on
    what static tools can't catch, instead of repeating them.
    """
    static_summary = "\n".join(
        f"- Line {f['line_number']}: {f['issue_type']} - {f['description']}"
        for f in static_findings
    ) or "None found."

    prompt = f"""You are a senior code reviewer analyzing a file from a pull request.

FILE: {filename}

STATIC ANALYSIS ALREADY FOUND THESE ISSUES:
{static_summary}

IMPORTANT RULE: Do not report any issue that is about the same root cause as
something in the list above, even if you describe it differently or from a
different angle (e.g. security risk, design concern, or suggestion framing
of the SAME underlying problem all count as repeats). Only report genuinely
NEW problems the static findings above do not already cover in any form.

CODE:
{code}

Analyze this code for:
1. Logical bugs (things that will behave incorrectly at runtime)
2. Design/architecture issues (poor structure, bad separation of concerns)
3. Security concerns NOT already covered above, in any framing
4. Concrete improvement suggestions NOT already covered above, in any framing

Respond ONLY with valid JSON, no markdown formatting, no backticks, no preamble.
Format exactly as this array structure:

[
  {{
    "line_number": <int or null>,
    "issue_type": "<bug|design|security|suggestion>",
    "severity": "<low|medium|high>",
    "description": "<clear, specific description>"
  }}
]

If you find nothing meaningful beyond what static analysis already caught, return an empty array: []
"""
    return prompt


def call_gemini_with_retry(prompt: str, max_retries: int = 3) -> str:
    """
    Calls Gemini, retrying on rate-limit (429) or server-overload (503) errors.
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )
            return response.text or ""

        except errors.ClientError as e:
            last_error = e
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt < max_retries:
                wait_time = 10
                print(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            raise

        except errors.ServerError as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 15
                print(f"Server overloaded (503), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError(f"Gemini call failed after {max_retries} retries: {last_error}")

def analyze_with_ai(filename: str, code: str, static_findings: list) -> list:
    """
    Sends code + static findings to Gemini, returns structured AI findings.
    """
    prompt = build_prompt(filename, code, static_findings)

    try:
        raw_text = call_gemini_with_retry(prompt).strip()

        # Safety: strip markdown code fences if the model adds them anyway
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        findings = json.loads(raw_text)

        issues = []
        for f in findings:
            issues.append({
                "file_name": filename,
                "line_number": f.get("line_number"),
                "issue_type": f.get("issue_type", "suggestion"),
                "severity": f.get("severity", "low"),
                "source": "ai",
                "description": f.get("description", "")
            })
        return issues

    except json.JSONDecodeError:
        print(f"Warning: AI response for {filename} wasn't valid JSON, skipping.")
        return []
    except Exception as e:
        print(f"Warning: AI analysis failed for {filename}: {e}")
        return []
    
def deduplicate_against_static(ai_issues: list, static_findings: list, line_tolerance: int = 1) -> list:
    """
    Removes AI findings only when they're on a nearby line AND
    topically overlap with a static finding (not just line proximity alone).
    """
    if not static_findings:
        return ai_issues

    filtered = []
    for issue in ai_issues:
        ai_line = issue.get('line_number')
        ai_text = (issue.get('description', '') + ' ' + issue.get('issue_type', '')).lower()

        if ai_line is None:
            filtered.append(issue)
            continue

        is_duplicate = False
        for static in static_findings:
            static_line = static.get('line_number')
            if static_line is None:
                continue
            if abs(ai_line - static_line) > line_tolerance:
                continue

            static_text = (static.get('description', '') + ' ' + static.get('issue_type', '')).lower()

            # Check topical overlap via shared keywords
            keywords = ['docstring', 'unused', 'password', 'secret', 'hardcod',
                        'naming', 'invalid-name', 'import']
            shared_keyword = any(
                kw in ai_text and kw in static_text for kw in keywords
            )

            if shared_keyword:
                is_duplicate = True
                break

        if not is_duplicate:
            filtered.append(issue)

    return filtered