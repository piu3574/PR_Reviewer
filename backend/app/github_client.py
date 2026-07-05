import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN is not set. Check your .env file.")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}


def parse_pr_url(pr_url: str):
    """
    Takes a GitHub PR URL like:
    https://github.com/owner/repo/pull/123
    and breaks it into owner, repo, pr_number
    """
    parts = pr_url.rstrip("/").split("/")
    owner = parts[-4]
    repo = parts[-3]
    pr_number = parts[-1]
    return owner, repo, pr_number


def fetch_pr_metadata(owner: str, repo: str, pr_number: str):
    """
    Fetches basic PR info: title, author, head commit sha, etc.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_pr_files(owner: str, repo: str, pr_number: str):
    """
    Fetches list of changed files in the PR, including their diffs.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_full_file_content(owner: str, repo: str, path: str, ref: str):
    """
    Fetches the complete content of a file at a specific commit/branch.
    'ref' is the commit SHA or branch name to fetch the file from.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": ref}
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()

    content_encoded = data.get("content", "")
    content = base64.b64decode(content_encoded).decode("utf-8")
    return content


def get_full_pr_data(pr_url: str):
    """
    Main function: given a PR link, returns metadata + files
    (with both diff and full file content) together.
    """
    owner, repo, pr_number = parse_pr_url(pr_url)
    metadata = fetch_pr_metadata(owner, repo, pr_number)
    files = fetch_pr_files(owner, repo, pr_number)

    head_sha = metadata.get("head", {}).get("sha")

    file_list = []
    for f in files:
        filename = f.get("filename")
        full_content = None

        if f.get("status") != "removed" and head_sha:
            try:
                full_content = fetch_full_file_content(owner, repo, filename, head_sha)
            except Exception:
                full_content = None

        file_list.append({
            "filename": filename,
            "diff": f.get("patch"),
            "full_content": full_content
        })

    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "title": metadata.get("title"),
        "author": metadata.get("user", {}).get("login"),
        "files": file_list
    }