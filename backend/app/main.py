from app.database import SessionLocal
from app.models import PullRequest, File, Issue
from app.github_client import get_full_pr_data
from app.static_analysis import analyze_python_file, analyze_js_file
from app.ai_analysis import analyze_with_ai
from typing import Optional
from app.ai_analysis import deduplicate_against_static
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.scoring import calculate_all_scores
from app.pdf_generator import generate_pdf_report
import os
from app.models import PullRequest, File, Issue, AnalysisResult
def save_pr_to_db(pr_url: str):
    """
    Fetches a PR from GitHub and saves it + its files into the database.
    """
    data = get_full_pr_data(pr_url)
    db = SessionLocal()

    try:
        pr = PullRequest(
            repo_name=f"{data['owner']}/{data['repo']}",
            pr_number=int(data['pr_number']),
            title=data['title'],
            author=data['author']
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)

        for f in data['files']:
            file_record = File(
                pull_request_id=pr.id,
                filename=f['filename'],
                diff=f['diff']
            )
            db.add(file_record)

        db.commit()
        print(f"Saved PR #{pr.pr_number} with {len(data['files'])} files. PR id = {pr.id}")
        return pr.id

    finally:
        db.close()


def analyze_and_save_issues(pr_id: int, pr_url: str):
    """
    Fetches PR files, runs static analysis on Python and JS files,
    and saves the resulting issues to the database.
    """
    data = get_full_pr_data(pr_url)
    db = SessionLocal()

    try:
        total_issues = 0
        for f in data['files']:
            filename = f['filename']
            code = f.get('full_content')

            if code is None:
                continue  # skip files we couldn't fetch full content for

            if filename.endswith('.py'):
                issues = analyze_python_file(code, filename)
            elif filename.endswith('.js') or filename.endswith('.jsx'):
                issues = analyze_js_file(code, filename)
            else:
                continue  # unsupported file type, skip

            for issue in issues:
                issue_record = Issue(
                    pull_request_id=pr_id,
                    file_name=issue['file_name'],
                    line_number=issue['line_number'],
                    issue_type=issue['issue_type'],
                    severity=issue['severity'],
                    source=issue['source'],
                    description=issue['description']
                )
                db.add(issue_record)
                total_issues += 1

        db.commit()
        print(f"Saved {total_issues} static analysis issues for PR id {pr_id}")

    finally:
        db.close()

def analyze_and_save_ai_issues(pr_id: int, pr_url: str):
    """
    Runs AI analysis on every file in the PR (any language), grounded
    with EXISTING static findings already saved in the DB for this PR,
    so the AI avoids repeating what static analysis already caught.
    """
    data = get_full_pr_data(pr_url)
    db = SessionLocal()

    try:
        # Pull existing static findings for this PR from the DB,
        # grouped by filename, so we can pass relevant context per file
        existing_static_issues = db.query(Issue).filter(
            Issue.pull_request_id == pr_id,
            Issue.source == "static"
        ).all()

        static_by_file = {}
        for issue in existing_static_issues:
            static_by_file.setdefault(issue.file_name, []).append({
                "line_number": issue.line_number,
                "issue_type": issue.issue_type,
                "description": issue.description
            })

        total_issues = 0
        for f in data['files']:
            filename = f['filename']
            code = f.get('full_content')

            if code is None:
                continue

            existing_static = static_by_file.get(filename, [])
            issues = analyze_with_ai(filename, code, existing_static)
            issues = deduplicate_against_static(issues, existing_static)

            for issue in issues:
                issue_record = Issue(
                    pull_request_id=pr_id,
                    file_name=issue['file_name'],
                    line_number=issue['line_number'],
                    issue_type=issue['issue_type'],
                    severity=issue['severity'],
                    source=issue['source'],
                    description=issue['description']
                )
                db.add(issue_record)
                total_issues += 1

        db.commit()
        print(f"Saved {total_issues} AI-generated issues for PR id {pr_id}")

    finally:
        db.close()

app = FastAPI(title="AI PR Review System")

# Allow the React frontend (running on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PRRequest(BaseModel):
    pr_url: str


@app.post("/analyze")
def analyze_pr(request: PRRequest):
    """
    Full pipeline: fetch PR -> static analysis -> AI analysis ->
    scoring -> PDF generation. Returns scores + issues + PDF path.
    """
    pr_url = request.pr_url

    try:
        pr_id = save_pr_to_db(pr_url)
        analyze_and_save_issues(pr_id, pr_url)
        analyze_and_save_ai_issues(pr_id, pr_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Analysis failed: {str(e)}")

    db = SessionLocal()
    try:
        pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
        issues_db = db.query(Issue).filter(Issue.pull_request_id == pr_id).all()

        issue_dicts = [
            {
                "file_name": i.file_name,
                "line_number": i.line_number,
                "issue_type": i.issue_type,
                "severity": i.severity,
                "source": i.source,
                "description": i.description
            }
            for i in issues_db
        ]

        scores = calculate_all_scores(issue_dicts)

        pr_data = {
            "owner": pr.repo_name.split("/")[0],
            "repo": pr.repo_name.split("/")[1],
            "pr_number": pr.pr_number,
            "title": pr.title,
            "author": pr.author,
            "files": []
        }

        os.makedirs("reports", exist_ok=True)
        pdf_filename = f"reports/pr_{pr_id}_report.pdf"
        generate_pdf_report(pr_data, issue_dicts, scores, pdf_filename)

        # Save scores to analysis_results table
        analysis_record = AnalysisResult(
            pull_request_id=pr_id,
            quality_score=scores['quality_score'],
            security_risk=scores['security_risk'],
            maintainability_score=scores['maintainability_score'],
            verdict=f"{scores['security_risk']} security risk, quality {scores['quality_score']}/10"
        )
        db.add(analysis_record)
        db.commit()

        return {
            "pr_id": pr_id,
            "pr_title": pr.title,
            "scores": scores,
            "issues": issue_dicts,
            "pdf_path": pdf_filename
        }

    finally:
        db.close()


@app.get("/report/{pr_id}")
def download_report(pr_id: int):
    """
    Serves the generated PDF for a given PR id.
    """
    from fastapi.responses import FileResponse
    pdf_path = f"reports/pr_{pr_id}_report.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"pr_{pr_id}_report.pdf")

@app.get("/history")
def get_history():
    """
    Returns all past analyzed PRs with their latest scores, most recent first.
    """
    db = SessionLocal()
    try:
        prs = db.query(PullRequest).order_by(PullRequest.id.desc()).all()

        history = []
        for pr in prs:
            latest_result = (
                db.query(AnalysisResult)
                .filter(AnalysisResult.pull_request_id == pr.id)
                .order_by(AnalysisResult.id.desc())
                .first()
            )
            history.append({
                "pr_id": pr.id,
                "repo_name": pr.repo_name,
                "pr_number": pr.pr_number,
                "title": pr.title,
                "author": pr.author,
                "quality_score": latest_result.quality_score if latest_result else None,
                "security_risk": latest_result.security_risk if latest_result else None,
                "maintainability_score": latest_result.maintainability_score if latest_result else None,
            })
        return {"history": history}
    finally:
        db.close()