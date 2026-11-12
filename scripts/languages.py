"""Build assets/languages.svg: top languages across public AND private repos.

Needs a token that can read your private repos (own + organizations), passed as
STATS_TOKEN. Only aggregated language totals are written to the SVG; no
repository names leave the script.

Counted: non-fork repos you own, collaborate on, or that belong to any of your
organizations, in which you authored at least one commit on the default branch.
Code size is scaled by your share of each repo's commits, so large shared
codebases you only touched lightly do not dominate.

Usage: STATS_TOKEN=... python scripts/languages.py
"""

import json
import math
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

TOKEN = os.environ.get("STATS_TOKEN")
OUT = Path(__file__).resolve().parent.parent / "assets" / "languages.svg"
TOP = 6
LABEL = "#8b949e"
BORDER = "#8b949e"
ACCENT = "#2c9ab7"
OTHER_COLOR = "#6e7681"


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


FIELDS = """pageInfo{hasNextPage endCursor}
  nodes{
    id isFork
    primaryLanguage{name color}
    languages(first:20,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}
    defaultBranchRef{target{...on Commit{all:history{totalCount} mine:history(author:{id:$id}){totalCount}}}}
  }"""

VIEWER_REPOS = """query($c:String,$id:ID!){viewer{repositories(first:25,after:$c,isFork:false,
  ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER]){%s}}}""" % FIELDS

ORG_REPOS = """query($o:String!,$c:String,$id:ID!){organization(login:$o){repositories(first:25,after:$c){%s}}}""" % FIELDS


def pages(query, variables, path):
    cursor = None
    while True:
        data = gql(query, {**variables, "c": cursor})
        for key in path:
            data = data[key]
        yield from data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            return
        cursor = data["pageInfo"]["endCursor"]


def collect():
    viewer = gql("{viewer{id organizations(first:100){nodes{login}}}}")["viewer"]
    uid = viewer["id"]
    orgs = [o["login"] for o in viewer["organizations"]["nodes"]]

    # The viewer's repository list misses some organization repos, so walk
    # every organization's repositories too and de-duplicate.
    seen = {}
    for n in pages(VIEWER_REPOS, {"id": uid}, ("viewer", "repositories")):
        seen[n["id"]] = n
    for org in orgs:
        for n in pages(ORG_REPOS, {"o": org, "id": uid}, ("organization", "repositories")):
            seen.setdefault(n["id"], n)

    by_bytes, by_commit, colors = Counter(), Counter(), {}
    repos = commits = 0
    for n in seen.values():
        if n["isFork"]:
            continue
        target = (n.get("defaultBranchRef") or {}).get("target") or {}
        mine = (target.get("mine") or {}).get("totalCount", 0)
        total_commits = (target.get("all") or {}).get("totalCount", 0) or mine
        if mine == 0:
            continue
        repos += 1
        commits += mine
        share = mine / total_commits  # only count your share of shared codebases
        edges = n["languages"]["edges"]
        size = sum(e["size"] for e in edges)
        for e in edges:
            name = e["node"]["name"]
            colors[name] = e["node"]["color"] or ACCENT
            by_bytes[name] += e["size"] * share
            if size:
                by_commit[name] += mine * e["size"] / size
        if not edges and n.get("primaryLanguage"):
            pl = n["primaryLanguage"]
            colors[pl["name"]] = pl["color"] or ACCENT
            by_commit[pl["name"]] += mine
    return by_bytes, by_commit, colors, repos, commits


def top(counter):
    total = sum(counter.values()) or 1
    items = counter.most_common(TOP)
    rest = total - sum(v for _, v in items)
    rows = [(k, v / total) for k, v in items]
    if rest / total >= 0.005:
        rows.append(("Other", rest / total))
    return rows


def donut(cx, cy, rows, colors):
    r, sw = 52, 22
    circ = 2 * math.pi * r
    out, offset = [], 0.0
    for name, frac in rows:
        length = frac * circ
        color = OTHER_COLOR if name == "Other" else colors.get(name, ACCENT)
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-dasharray="{length:.2f} {circ - length:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"><title>{name} {frac * 100:.1f}%</title></circle>'
        )
        offset += length
    return "".join(out)


def legend(x, y, rows, colors):
    out = []
    for i, (name, frac) in enumerate(rows):
        yy = y + i * 21
        color = OTHER_COLOR if name == "Other" else colors.get(name, ACCENT)
        out.append(
            f'<rect x="{x}" y="{yy - 9}" width="10" height="10" rx="2" fill="{color}"/>'
            f'<text x="{x + 17}" y="{yy}" class="n">{name}</text>'
            f'<text x="{x + 175}" y="{yy}" class="p" text-anchor="end">{frac * 100:.1f}%</text>'
        )
    return "".join(out)


def render(by_bytes, by_commit, colors, repos, commits):
    W, H = 840, 245
    panels = [("Languages by code written", top(by_bytes)), ("Languages by commits", top(by_commit))]
    body = []
    for i, (title, rows) in enumerate(panels):
        ox = 20 + i * 410
        body.append(f'<text x="{ox + 20}" y="40" class="t">{title}</text>')
        body.append(donut(ox + 90, 130, rows, colors))
        body.append(legend(ox + 180, 82, rows, colors))
    body.append(
        f'<text x="{W / 2}" y="{H - 14}" class="a" text-anchor="middle">'
        f"Public + private: {repos} repositories, {commits:,} commits on default branches</text>"
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Top languages across public and private repositories">
<style>
  text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }}
  .t {{ font-size: 16px; font-weight: 600; fill: {ACCENT}; }}
  .n {{ font-size: 13px; fill: {LABEL}; }}
  .p {{ font-size: 13px; font-weight: 600; fill: {LABEL}; }}
  .a {{ font-size: 11px; fill: {LABEL}; }}
</style>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="none" stroke="{BORDER}" stroke-opacity="0.35"/>
<line x1="{W / 2}" y1="25" x2="{W / 2}" y2="{H - 40}" stroke="{BORDER}" stroke-opacity="0.2"/>
{''.join(body)}
</svg>
"""


def main():
    if not TOKEN:
        print("STATS_TOKEN not set: skipping languages card (existing file kept).")
        return
    by_bytes, by_commit, colors, repos, commits = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(by_bytes, by_commit, colors, repos, commits), encoding="utf-8")
    print(f"repos={repos} commits={commits}")
    print("bytes: ", top(by_bytes))
    print("commit:", top(by_commit))


if __name__ == "__main__":
    sys.exit(main())
