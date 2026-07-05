# Severity weights used for general quality/maintainability scoring.
# Higher severity issues count more heavily against the score.
SEVERITY_WEIGHTS = {
    "high": 3,
    "medium": 2,
    "low": 1
}

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}

# Known dangerous patterns and their MINIMUM real-world risk level,
# regardless of what severity the originating tool assigned.
# This exists because tool-reported severity reflects tool confidence,
# not actual real-world impact. A hardcoded password is high-risk even
# if bandit itself rates its confidence as "low".
KNOWN_RISK_FLOORS = {
    # Bandit security checks (bandit test IDs)
    "b105": "high",     # hardcoded password (string)
    "b106": "high",     # hardcoded password (function arg default)
    "b107": "high",     # hardcoded password (function arg default, alt form)
    "b108": "medium",   # insecure temp file usage
    "b301": "high",     # pickle usage (deserialization risk)
    "b303": "medium",   # insecure hash function (MD5/SHA1)
    "b311": "low",      # standard pseudo-random generators (not crypto-safe)
    "b608": "high",     # possible SQL injection
    "b703": "high",     # django mark_safe (XSS risk)

    # eslint security-relevant rules
    "no-eval": "high",  # eval() usage
}

# Issue types considered maintainability-related (style/structure, not bugs/security)
MAINTAINABILITY_TYPES = [
    "missing-module-docstring", "missing-function-docstring",
    "invalid-name", "unused-import", "unused-vars", "no-unused-vars",
    "design"
]


def is_security_issue(issue: dict) -> bool:
    """
    Determines if an issue counts as security-relevant at all -
    either explicitly tagged, a known bandit code, or matches
    security-related keywords in its description.
    """
    issue_type = (issue.get("issue_type") or "").lower()
    description = (issue.get("description") or "").lower()

    if issue_type == "security":
        return True
    if issue_type in KNOWN_RISK_FLOORS:
        return True
    if issue_type.startswith("b") and issue_type[1:].isdigit():
        return True  # any bandit code (B1xx, B3xx, B6xx, etc.)

    security_keywords = ["password", "secret", "injection", "eval(",
                          "pickle", "hash", "encrypt", "vulnerab", "xss", "csrf"]
    return any(kw in description for kw in security_keywords)


def classify_security_severity(issue: dict) -> str:
    """
    Determines the EFFECTIVE severity of a security-relevant issue,
    taking the higher of: (a) the tool's reported severity, or
    (b) a known risk floor for that issue type/topic, if one applies.
    """
    issue_type = (issue.get("issue_type") or "").lower()
    description = (issue.get("description") or "").lower()
    reported_severity = (issue.get("severity") or "low").lower()

    floor = KNOWN_RISK_FLOORS.get(issue_type)

    if floor is None:
        danger_keywords = {
            "high": ["hardcoded password", "hardcoded secret", "sql injection",
                     "command injection", "eval(", "pickle", "deserializ"],
            "medium": ["insecure hash", "weak encryption", "temp file", "cleartext"]
        }
        for level, keywords in danger_keywords.items():
            if any(kw in description or kw in issue_type for kw in keywords):
                floor = level
                break

    if floor is None:
        return reported_severity  # no known floor, trust the tool's rating

    reported_rank = SEVERITY_RANK.get(reported_severity, 1)
    floor_rank = SEVERITY_RANK.get(floor, 1)
    effective_rank = max(reported_rank, floor_rank)

    for level, rank in SEVERITY_RANK.items():
        if rank == effective_rank:
            return level
    return reported_severity


def get_effective_severity(issue: dict) -> str:
    """
    Returns the effective severity for ANY issue - applies the
    security risk floor if relevant, otherwise returns the tool's
    own severity rating as-is.
    """
    if is_security_issue(issue):
        return classify_security_severity(issue)
    return (issue.get("severity") or "low").lower()


def calculate_quality_score(issues: list) -> float:
    """
    Deterministic score from 0-10 based on weighted issue count,
    using EFFECTIVE severity (accounts for known risk floors on
    security issues, not just the raw tool-reported severity).
    """
    if not issues:
        return 10.0

    total_weight = sum(
        SEVERITY_WEIGHTS.get(get_effective_severity(i), 1) for i in issues
    )

    score = 10 - (total_weight / 5)
    return round(max(0.0, min(10.0, score)), 1)


def calculate_security_risk(issues: list) -> str:
    """
    Security risk level based on EFFECTIVE severity (tool rating OR
    known risk floor, whichever is higher) of all security-relevant issues.
    """
    security_issues = [i for i in issues if is_security_issue(i)]

    if not security_issues:
        return "Low"

    effective_severities = [classify_security_severity(i) for i in security_issues]

    if "high" in effective_severities:
        return "High"
    elif "medium" in effective_severities or len(effective_severities) >= 2:
        return "Medium"
    else:
        return "Low"


def calculate_maintainability_score(issues: list) -> float:
    """
    Maintainability score based on style/design-related issues specifically
    (docstrings, naming, unused code, design issues) - separate from
    overall quality, which includes bugs/security too.
    """
    relevant_issues = [
        i for i in issues
        if (i.get("issue_type") or "").lower() in MAINTAINABILITY_TYPES
    ]

    if not relevant_issues:
        return 10.0

    total_weight = sum(
        SEVERITY_WEIGHTS.get(get_effective_severity(i), 1) for i in relevant_issues
    )
    score = 10 - (total_weight / 4)
    return round(max(0.0, min(10.0, score)), 1)


def calculate_all_scores(issues: list) -> dict:
    """
    Runs all scoring functions and returns a combined result.
    issues should be a list of dicts with at least 'severity' and
    'issue_type' keys (and optionally 'description' for keyword matching).
    """
    return {
        "quality_score": calculate_quality_score(issues),
        "security_risk": calculate_security_risk(issues),
        "maintainability_score": calculate_maintainability_score(issues)
    }