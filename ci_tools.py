"""Helpers for the GitHub Actions workflow (.github/workflows/daily.yml).

    python ci_tools.py commit   commit and push today's results (data/ and images/) back to the repository
    python ci_tools.py notify   optional: open a GitHub issue listing today's changes (not used by the workflow)

Uses only the workflow's built-in GITHUB_TOKEN; no other credentials are needed.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# Lines in the changes report that mean someone should look. "NOT ON TRACKER" alone is routine for approved projects.
NEEDS_ATTENTION = ("ACT ON THIS", "NEW PROJECT", "NEW RECORD", "NEW DOCUMENT", "STATUS", "APPEAL PERIOD", "WARNING")


def today_report():
    path = os.path.join(HERE, "data", "changes", f"{dt.date.today().isoformat()}.txt")
    try:
        with open(path) as f:
            return [line.rstrip() for line in f if line.strip()]
    except OSError:
        return []


def api(method, path, body=None):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def notify():
    lines = [l for l in today_report() if l.startswith(NEEDS_ATTENTION) or "ACT ON THIS" in l]
    if not lines:
        print("Nothing needs attention today; no issue opened.")
        return
    title = f"City changes to review: {dt.date.today().strftime('%b %-d, %Y')}"
    open_issues = api("GET", "/issues?state=open&per_page=100")
    if any(i.get("title") == title for i in open_issues):
        print("An issue for today already exists.")
        return
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    body = ("The daily check found changes on the City of Boise case files.\n\n```\n" + "\n".join(lines) + "\n```\n\n"
            "**To update the report:** open the case on permits.cityofboise.org, read the new documents, and edit "
            "`data/projects.json` following [EDITING_GUIDE.md](../blob/main/EDITING_GUIDE.md) (stage, timeline, flags, "
            "attributes, new drawings, notice areas). Committing the edit to `main` republishes the page automatically.\n\n"
            f"Full report: `data/changes/{dt.date.today().isoformat()}.txt` · [Workflow run]({run_url})\n\n"
            "Close this issue when the report is updated.")
    issue = api("POST", "/issues", {"title": title, "body": body})
    print(f"Opened issue #{issue['number']}: {issue['html_url']}")


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=HERE, check=check, capture_output=True, text=True)


def commit():
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898283+github-actions[bot]@users.noreply.github.com")
    git("add", "-A", "data/", "images/")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("No data changes to save.")
        return
    git("commit", "-m", f"Daily city check {dt.date.today().isoformat()}")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    pulled = git("pull", "--rebase", "origin", branch, check=False)
    if pulled.returncode != 0:
        sys.exit("Could not merge with changes pushed during this run. Re-run the workflow.\n" + pulled.stderr)
    git("push", "origin", f"HEAD:{branch}")
    print("Saved today's results to the repository.")


if __name__ == "__main__":
    {"notify": notify, "commit": commit}[sys.argv[1]]()
