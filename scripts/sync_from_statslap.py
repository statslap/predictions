#!/usr/bin/env python3
"""Sync the public predictions log from the StatSlap project.

Reads the StatSlap pending predictions + queries result APIs (football-data,
OpenLigaDB) to settle finished matches, then writes one JSON per kickoff day
into predictions/. Re-runs build_index.py and stages a git commit (if a git
repo is present), but does NOT push by default.

Usage:
    python3 scripts/sync_from_statslap.py            # just rebuild files
    python3 scripts/sync_from_statslap.py --commit   # also git add + commit
    python3 scripts/sync_from_statslap.py --push     # also git push
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATSLAP = Path("/Users/Jorgos/StatSlap")
PENDING = STATSLAP / "src/data/ou_pending_predictions.json"
ENV = STATSLAP / ".env"


def load_env() -> None:
    if not ENV.exists():
        return
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def fd_match(mid: int) -> dict | None:
    api = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not api:
        return None
    try:
        req = urllib.request.Request(
            f"https://api.football-data.org/v4/matches/{mid}",
            headers={"X-Auth-Token": api},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception:
        return None


def bl2_match(mid: int) -> dict | None:
    try:
        with urllib.request.urlopen(
            f"https://api.openligadb.de/getmatchdata/{mid}", timeout=10
        ) as r:
            return json.load(r)
    except Exception:
        return None


def settle_fd(mid: int, p: dict) -> dict:
    m = fd_match(mid) or {}
    sc = (m.get("score") or {}).get("fullTime") or {}
    h, a = sc.get("home"), sc.get("away")
    tot = (h or 0) + (a or 0) if h is not None else None
    won = (tot > 2.5) if tot is not None else None
    utc = m.get("utcDate") or p.get("kickoff_utc") or ""
    day = (utc[:10]) if utc else "unknown"
    return {
        "match_id": mid,
        "home": p.get("home"),
        "away": p.get("away"),
        "competition": p.get("competition"),
        "kickoff_utc": utc,
        "kickoff": p.get("kickoff"),
        "prediction": "OVER 2.5",
        "p_model": p.get("p_taken"),
        "lambda_total": p.get("lambda_total"),
        "final_score": f"{h}-{a}" if h is not None else None,
        "final_total": tot,
        "result": "HIT" if won else ("MISS" if won is False else "PENDING"),
        "status": m.get("status"),
        "captured_at": p.get("captured_at"),
        "_day": day,
    }


def settle_bl2(mid: int, p: dict) -> dict:
    m = bl2_match(mid) or {}
    results_arr = m.get("matchResults") or []
    final = next((r for r in results_arr if r.get("resultName") == "Endergebnis"), None)
    if final:
        ph, pa = final.get("pointsTeam1"), final.get("pointsTeam2")
        tot = ph + pa
        won = tot > 2.5
        score = f"{ph}-{pa}"
        stat = "FINISHED"
    else:
        ph = pa = tot = won = score = None
        stat = "NOT_FINISHED"
    utc = m.get("matchDateTimeUTC") or p.get("kickoff_utc") or ""
    day = (utc[:10]) if utc else "unknown"
    return {
        "match_id": mid,
        "home": p.get("home"),
        "away": p.get("away"),
        "competition": p.get("competition"),
        "kickoff_utc": utc,
        "kickoff": p.get("kickoff"),
        "prediction": "OVER 2.5",
        "p_model": p.get("p_taken"),
        "lambda_total": p.get("lambda_total"),
        "final_score": score,
        "final_total": tot,
        "result": "HIT" if won else ("MISS" if won is False else "PENDING"),
        "status": stat,
        "captured_at": p.get("captured_at"),
        "_day": day,
    }


def is_bl2_id(mid: int) -> bool:
    # OpenLigaDB BL2 ids are typically 5-digit
    return mid < 100_000


def main() -> int:
    load_env()
    if not PENDING.exists():
        print(f"No pending file at {PENDING}", file=sys.stderr)
        return 1

    raw = json.loads(PENDING.read_text())
    items = []
    for k, v in raw.items():
        if k == "predictions":
            continue
        if isinstance(v, dict) and v.get("match_id"):
            items.append(v)

    settled = []
    for p in items:
        mid = int(p["match_id"])
        rec = settle_bl2(mid, p) if is_bl2_id(mid) else settle_fd(mid, p)
        settled.append(rec)

    by_day: dict[str, list[dict]] = {}
    for r in settled:
        d = r.pop("_day") or "unknown"
        if d == "unknown":
            continue
        by_day.setdefault(d, []).append(r)

    written = 0
    for day, preds in sorted(by_day.items()):
        out = {
            "date": day,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_version": "independent_poisson_v11",
            "predictions": preds,
            "summary": {
                "total": len(preds),
                "hits": sum(1 for r in preds if r["result"] == "HIT"),
                "misses": sum(1 for r in preds if r["result"] == "MISS"),
                "pending": sum(1 for r in preds if r["result"] == "PENDING"),
            },
        }
        path = ROOT / "predictions" / f"{day}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        written += 1

    # Rebuild index manifest
    subprocess.run([sys.executable, str(ROOT / "scripts/build_index.py")], check=True)
    print(f"Synced {written} day(s) from {len(items)} pending predictions")

    if "--commit" in sys.argv or "--push" in sys.argv:
        subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"sync: {written} day(s) updated — {ts}"
        # Allow empty for idempotent runs
        r = subprocess.run(
            ["git", "-C", str(ROOT), "commit", "-m", msg],
            capture_output=True, text=True,
        )
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(r.stdout); print(r.stderr, file=sys.stderr)
            return 2
        print(r.stdout.strip() or "no changes to commit")

    if "--push" in sys.argv:
        subprocess.run(["git", "-C", str(ROOT), "push"], check=True)
        print("pushed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
