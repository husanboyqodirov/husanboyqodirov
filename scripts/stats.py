"""Build assets/stats.svg from the GitHub contribution calendar.

The calendar includes private contributions when "Private contributions" is
enabled on the profile, so the built-in GITHUB_TOKEN is enough.

Usage: GITHUB_TOKEN=... python scripts/stats.py [username]
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

USER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("STATS_USER", "husanboyqodirov")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(__file__).resolve().parent.parent / "assets" / "stats.svg"

ACCENT = "#2c9ab7"
LABEL = "#8b949e"
BORDER = "#8b949e"


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def calendar(start, end):
    q = """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
      contributionsCollection(from:$f,to:$t){contributionCalendar{
        totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
    data = gql(q, {"u": USER, "f": start.isoformat(), "t": end.isoformat()})
    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    return cal["totalContributions"], days


def main():
    created = gql("query($u:String!){user(login:$u){createdAt}}", {"u": USER})["user"]["createdAt"]
    first_year = int(created[:4])
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()

    all_time = 0
    by_date = {}
    this_year = 0
    for year in range(first_year, today.year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
        total, days = calendar(start, end)
        all_time += total
        if year == today.year:
            this_year = total
        for d in days:
            by_date[d["date"]] = d["contributionCount"]

    dates = sorted(by_date)

    # Longest streak
    longest = run = 0
    prev = None
    for ds in dates:
        d = dt.date.fromisoformat(ds)
        if by_date[ds] > 0:
            run = run + 1 if prev and (d - prev).days == 1 and by_date[prev.isoformat()] > 0 else 1
            longest = max(longest, run)
        prev = d

    # Current streak (today may still be empty; then count from yesterday)
    cur = 0
    d = today
    if by_date.get(d.isoformat(), 0) == 0:
        d -= dt.timedelta(days=1)
    while by_date.get(d.isoformat(), 0) > 0:
        cur += 1
        d -= dt.timedelta(days=1)

    # Last 52 weeks, weekly totals
    weeks = []
    start = today - dt.timedelta(days=7 * 52 - 1)
    for i in range(52):
        ws = start + dt.timedelta(days=7 * i)
        weeks.append(sum(by_date.get((ws + dt.timedelta(days=k)).isoformat(), 0) for k in range(7)))
    last_year = sum(weeks)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(all_time, this_year, last_year, cur, longest, weeks, today, first_year), encoding="utf-8")
    print(f"all_time={all_time} this_year={this_year} last_52w={last_year} current={cur} longest={longest}")


def fmt(n):
    return f"{n:,}"


def render(all_time, this_year, last_year, cur, longest, weeks, today, first_year):
    W, H = 840, 250
    tiles = [
        (fmt(all_time), f"Contributions since {first_year}"),
        (fmt(last_year), "In the last 12 months"),
        (fmt(this_year), f"In {today.year}"),
        (f"{cur} / {longest}", "Current / longest streak (days)"),
    ]
    tw = (W - 40) / len(tiles)
    parts = []
    for i, (val, lab) in enumerate(tiles):
        x = 20 + tw * i + tw / 2
        parts.append(
            f'<text x="{x:.1f}" y="74" class="v" text-anchor="middle">{val}</text>'
            f'<text x="{x:.1f}" y="100" class="l" text-anchor="middle">{lab}</text>'
        )

    # Weekly bars
    cx, cy, cw, ch = 30, 130, W - 60, 80
    peak = max(weeks) or 1
    bw = cw / len(weeks)
    bars = []
    for i, n in enumerate(weeks):
        h = max(2, ch * n / peak) if n else 2
        op = 0.25 if n == 0 else 0.45 + 0.55 * n / peak
        bars.append(
            f'<rect x="{cx + i * bw + 1:.1f}" y="{cy + ch - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" '
            f'rx="1.5" fill="{ACCENT}" fill-opacity="{op:.2f}"><title>{n} contributions</title></rect>'
        )
    first = today - dt.timedelta(days=7 * 52 - 1)
    axis = (
        f'<text x="{cx}" y="{cy + ch + 20}" class="a">{first:%b %Y}</text>'
        f'<text x="{cx + cw}" y="{cy + ch + 20}" class="a" text-anchor="end">{today:%b %Y}</text>'
        f'<text x="{W / 2}" y="{cy + ch + 20}" class="a" text-anchor="middle">Weekly contributions, public + private</text>'
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub contributions: {fmt(all_time)} since {first_year}">
<style>
  text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }}
  .v {{ font-size: 30px; font-weight: 700; fill: {ACCENT}; }}
  .l {{ font-size: 13px; fill: {LABEL}; }}
  .a {{ font-size: 11px; fill: {LABEL}; }}
</style>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="none" stroke="{BORDER}" stroke-opacity="0.35"/>
{''.join(parts)}
<line x1="{cx}" y1="{cy + ch + 0.5}" x2="{cx + cw}" y2="{cy + ch + 0.5}" stroke="{BORDER}" stroke-opacity="0.35"/>
{''.join(bars)}
{axis}
<!-- updated {today.isoformat()} -->
</svg>
"""


if __name__ == "__main__":
    main()
