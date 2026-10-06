"""Append public PR repositories to the three-column contribution table."""

import html
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

START = "      <!-- contributions:start -->"
END = "      <!-- contributions:end -->"
QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      nodes { repository { name nameWithOwner isPrivate owner { login avatarUrl(size: 64) } } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def fetch_repositories(login):
    repositories = {}
    cursor = None
    while True:
        response = subprocess.run(
            ["gh", "api", "graphql", "--input", "-"],
            input=json.dumps({"query": QUERY, "variables": {"login": login, "cursor": cursor}}),
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        payload = json.loads(response.stdout)
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        page = payload["data"]["user"]["pullRequests"]
        for node in page["nodes"]:
            repo = node["repository"]
            if not repo["isPrivate"] and repo["owner"]["login"].casefold() != login.casefold():
                repositories.setdefault(repo["nameWithOwner"].casefold(), repo)
        if not page["pageInfo"]["hasNextPage"]:
            return list(repositories.values())
        cursor = page["pageInfo"]["endCursor"]


def update_readme(readme, repositories, login):
    before, section = readme.split(START, 1)
    current, after = section.split(END, 1)
    cells = re.findall(r"<td>.*?</td>", current, re.DOTALL)
    existing = {
        name.casefold()
        for name in re.findall(r'https://github.com/([^/]+/[^/]+)/pulls\?', current)
    }
    added = []
    for repo in repositories:
        name = repo["nameWithOwner"]
        if name.casefold() in existing:
            continue
        url = f"https://github.com/{name}/pulls?q=" + quote(f"is:pr author:{login}", safe="")
        avatar = html.escape(repo["owner"]["avatarUrl"], quote=True)
        label = html.escape(repo["name"])
        cells.append(
            f'<td><a href="{url}"><img src="{avatar}" alt="" width="28" height="28" />'
            f'<br />{label}</a></td>'
        )
        existing.add(name.casefold())
        added.append(name)
    if not added:
        return readme, added
    lines = ["      <table>"]
    for offset in range(0, len(cells), 3):
        lines.append("        <tr>")
        lines.extend(f"          {cell}" for cell in cells[offset:offset + 3])
        lines.append("        </tr>")
    lines.append("      </table>")
    return before + START + "\n" + "\n".join(lines) + "\n" + END + after, added


if __name__ == "__main__":
    login = os.environ["PROFILE_USER"]
    path = Path("README.md")
    readme = path.read_text(encoding="utf-8")
    updated, added = update_readme(readme, fetch_repositories(login), login)
    if added:
        path.write_text(updated, encoding="utf-8")
        print("Added: " + ", ".join(added))
    else:
        print("No new contribution repositories.")
