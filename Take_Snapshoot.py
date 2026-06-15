"""
Albion Online Guild Daily Statistics Tracker
=============================================
Fetches guild member stats from the official API, computes daily deltas
(today minus yesterday), stores snapshots + daily leaderboards in SQLite,
and prints a ranked Top-5 report for every fame category.

Usage
-----
    python albion_guild_stats.py

First run: snapshots today's data (no delta possible yet).
Every subsequent run: computes the daily delta and saves the leaderboard.

Schedule with cron (once per day, e.g. 23:55):
    55 23 * * * /usr/bin/python3 /path/to/albion_guild_stats.py >> /var/log/albion_stats.log 2>&1

Configuration
-------------
Edit the CONSTANTS section below before running.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import json
import os

import requests

# ──────────────────────────────────────────────
# CONSTANTS  –  edit these before running
# ──────────────────────────────────────────────
DB_PATH    = Path("albion_guild_stats.db")      # SQLite file location
TOP_N      = 5                                  # how many players per category
REQUEST_TIMEOUT = 15                            # seconds
# Replace with this:
def _load_guild_id() -> str:
    # 1. Environment variable (GitHub Actions secret)
    env_id = os.environ.get("ALBION_GUILD_ID", "").strip()
    if env_id:
        return env_id
    # 2. config.json
    config_path = Path("config.json")
    if config_path.exists():
        with config_path.open() as fh:
            cfg = json.load(fh)
        guild_id = cfg.get("guild_id", "").strip()
        if guild_id:
            return guild_id
    raise ValueError("ALBION_GUILD_ID not found in env vars or config.json")

GUILD_ID = _load_guild_id()
API_URL  = f"https://gameinfo-ams.albiononline.com/api/gameinfo/guilds/{GUILD_ID}/members"

# Fame categories: (display_name, extractor_function)
# Each extractor receives one member dict and returns an int.
CATEGORIES = [
    ("Kill Fame",      lambda m: m.get("KillFame", 0) or 0),
    ("Death Fame",     lambda m: m.get("DeathFame", 0) or 0),
    ("PvE Fame",       lambda m: (m.get("LifetimeStatistics") or {}).get("PvE", {}).get("Total", 0) or 0),
    ("Gathering Fame", lambda m: (m.get("LifetimeStatistics") or {}).get("Gathering", {}).get("All", {}).get("Total", 0) or 0),
    ("Crafting Fame",  lambda m: (m.get("LifetimeStatistics") or {}).get("Crafting", {}).get("Total", 0) or 0),
]

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════════

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist yet."""
    conn.executescript("""
    -- Raw snapshot: one row per player per fetch
    CREATE TABLE IF NOT EXISTS snapshots (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        fetched_at    TEXT    NOT NULL,          -- ISO-8601 UTC timestamp
        snapshot_date TEXT    NOT NULL,          -- YYYY-MM-DD (local date at fetch time)
        player_id     TEXT    NOT NULL,
        player_name   TEXT    NOT NULL,
        guild_name    TEXT    NOT NULL,
        kill_fame     INTEGER NOT NULL DEFAULT 0,
        death_fame    INTEGER NOT NULL DEFAULT 0,
        pve_fame      INTEGER NOT NULL DEFAULT 0,
        gathering_fame INTEGER NOT NULL DEFAULT 0,
        crafting_fame INTEGER NOT NULL DEFAULT 0,
        UNIQUE (snapshot_date, player_id)
    );

    -- Daily deltas: computed from consecutive snapshots
    CREATE TABLE IF NOT EXISTS daily_deltas (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        stat_date       TEXT    NOT NULL,        -- the day this delta represents
        player_id       TEXT    NOT NULL,
        player_name     TEXT    NOT NULL,
        kill_fame_delta     INTEGER NOT NULL DEFAULT 0,
        death_fame_delta    INTEGER NOT NULL DEFAULT 0,
        pve_fame_delta      INTEGER NOT NULL DEFAULT 0,
        gathering_fame_delta INTEGER NOT NULL DEFAULT 0,
        crafting_fame_delta  INTEGER NOT NULL DEFAULT 0,
        UNIQUE (stat_date, player_id)
    );

    -- Leaderboard: Top-N per category per day
    CREATE TABLE IF NOT EXISTS leaderboard (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        stat_date    TEXT    NOT NULL,
        category     TEXT    NOT NULL,
        rank         INTEGER NOT NULL,
        player_id    TEXT    NOT NULL,
        player_name  TEXT    NOT NULL,
        fame_delta   INTEGER NOT NULL,
        UNIQUE (stat_date, category, rank)
    );

    -- Run log: one row per script execution for diagnostics
    CREATE TABLE IF NOT EXISTS run_log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at        TEXT    NOT NULL,
        status        TEXT    NOT NULL,          -- 'ok' | 'error' | 'first_run'
        members_fetched INTEGER,
        delta_computed  INTEGER,                 -- 1 if delta was computed, 0 if first run
        message       TEXT
    );
    """)
    conn.commit()
    log.info("Database initialised at %s", DB_PATH.resolve())


# ════════════════════════════════════════════════════════════════
# API
# ════════════════════════════════════════════════════════════════

def fetch_members() -> list[dict]:
    """Download current guild member list from the Albion API."""
    log.info("Fetching guild data from %s", API_URL)
    resp = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data)}")
    log.info("Received %d member records", len(data))
    return data


# ════════════════════════════════════════════════════════════════
# SNAPSHOT
# ════════════════════════════════════════════════════════════════

def save_snapshot(conn: sqlite3.Connection, members: list[dict], today: str) -> None:
    """Upsert today's snapshot for every member."""
    rows = []
    for m in members:
        rows.append((
            datetime.now(timezone.utc).isoformat(),
            today,
            m.get("Id", ""),
            m.get("Name", "Unknown"),
            m.get("GuildName", ""),
            CATEGORIES[0][1](m),   # Kill Fame
            CATEGORIES[1][1](m),   # Death Fame
            CATEGORIES[2][1](m),   # PvE Fame
            CATEGORIES[3][1](m),   # Gathering Fame
            CATEGORIES[4][1](m),   # Crafting Fame
        ))

    conn.executemany("""
        INSERT INTO snapshots
            (fetched_at, snapshot_date, player_id, player_name, guild_name,
             kill_fame, death_fame, pve_fame, gathering_fame, crafting_fame)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(snapshot_date, player_id) DO UPDATE SET
            fetched_at     = excluded.fetched_at,
            player_name    = excluded.player_name,
            kill_fame      = excluded.kill_fame,
            death_fame     = excluded.death_fame,
            pve_fame       = excluded.pve_fame,
            gathering_fame = excluded.gathering_fame,
            crafting_fame  = excluded.crafting_fame
    """, rows)
    conn.commit()
    log.info("Snapshot saved for %d members on %s", len(rows), today)


# ════════════════════════════════════════════════════════════════
# DELTA COMPUTATION
# ════════════════════════════════════════════════════════════════

def get_previous_snapshot_date(conn: sqlite3.Connection, today: str) -> str | None:
    """Return the most recent snapshot date before today, or None."""
    row = conn.execute("""
        SELECT snapshot_date FROM snapshots
        WHERE snapshot_date < ?
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        LIMIT 1
    """, (today,)).fetchone()
    return row["snapshot_date"] if row else None


def load_snapshot_dict(conn: sqlite3.Connection, snapshot_date: str) -> dict[str, sqlite3.Row]:
    """Return {player_id: row} for a given snapshot date."""
    rows = conn.execute("""
        SELECT * FROM snapshots WHERE snapshot_date = ?
    """, (snapshot_date,)).fetchall()
    return {r["player_id"]: r for r in rows}


def compute_deltas(
    today_snap: dict[str, sqlite3.Row],
    prev_snap:  dict[str, sqlite3.Row],
    stat_date:  str,
) -> list[dict]:
    """Compute per-player daily fame deltas."""
    fame_cols = ["kill_fame", "death_fame", "pve_fame", "gathering_fame", "crafting_fame"]
    deltas = []
    for pid, today_row in today_snap.items():
        prev_row = prev_snap.get(pid)
        if prev_row is None:
            # New member — no baseline to diff against, skip to avoid
            # counting their entire lifetime fame as a single day
            continue

        prev_values = {c: prev_row[c] for c in fame_cols}

        delta = {
            "stat_date":   stat_date,
            "player_id":   pid,
            "player_name": today_row["player_name"],
        }
        for col in fame_cols:
            raw = today_row[col] - prev_values[col]
            delta[f"{col}_delta"] = max(raw, 0)
        deltas.append(delta)
    return deltas

def save_deltas(conn: sqlite3.Connection, deltas: list[dict]) -> None:
    conn.executemany("""
        INSERT INTO daily_deltas
            (stat_date, player_id, player_name,
             kill_fame_delta, death_fame_delta, pve_fame_delta,
             gathering_fame_delta, crafting_fame_delta)
        VALUES
            (:stat_date, :player_id, :player_name,
             :kill_fame_delta, :death_fame_delta, :pve_fame_delta,
             :gathering_fame_delta, :crafting_fame_delta)
        ON CONFLICT(stat_date, player_id) DO UPDATE SET
            player_name           = excluded.player_name,
            kill_fame_delta       = excluded.kill_fame_delta,
            death_fame_delta      = excluded.death_fame_delta,
            pve_fame_delta        = excluded.pve_fame_delta,
            gathering_fame_delta  = excluded.gathering_fame_delta,
            crafting_fame_delta   = excluded.crafting_fame_delta
    """, deltas)
    conn.commit()
    log.info("Saved %d delta rows for %s", len(deltas), deltas[0]["stat_date"] if deltas else "—")


# ════════════════════════════════════════════════════════════════
# LEADERBOARD
# ════════════════════════════════════════════════════════════════

# Maps category display name → delta column in daily_deltas
CATEGORY_COL = {
    "Kill Fame":      "kill_fame_delta",
    "Death Fame":     "death_fame_delta",
    "PvE Fame":       "pve_fame_delta",
    "Gathering Fame": "gathering_fame_delta",
    "Crafting Fame":  "crafting_fame_delta",
}


def build_leaderboard(conn: sqlite3.Connection, stat_date: str) -> dict[str, list[dict]]:
    """Return Top-N players per category for a given stat_date."""
    leaderboard = {}
    for cat, col in CATEGORY_COL.items():
        rows = conn.execute(f"""
            SELECT player_name, {col} AS fame_delta
            FROM daily_deltas
            WHERE stat_date = ?
            ORDER BY {col} DESC
            LIMIT ?
        """, (stat_date, TOP_N)).fetchall()
        leaderboard[cat] = [dict(r) for r in rows]
    return leaderboard


def save_leaderboard(conn: sqlite3.Connection, stat_date: str, leaderboard: dict) -> None:
    rows = []
    for cat, entries in leaderboard.items():
        for rank, entry in enumerate(entries, start=1):
            rows.append((
                stat_date, cat, rank,
                entry.get("player_id", ""),
                entry["player_name"],
                entry["fame_delta"],
            ))
    conn.executemany("""
        INSERT INTO leaderboard
            (stat_date, category, rank, player_id, player_name, fame_delta)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(stat_date, category, rank) DO UPDATE SET
            player_id   = excluded.player_id,
            player_name = excluded.player_name,
            fame_delta  = excluded.fame_delta
    """, rows)
    conn.commit()
    log.info("Leaderboard saved (%d rows)", len(rows))


# ════════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════════

def print_report(stat_date: str, leaderboard: dict) -> None:
    """Pretty-print the daily Top-N report to stdout."""
    width = 60
    print()
    print("═" * width)
    print(f"  🏆  ALBION GUILD DAILY FAME REPORT — {stat_date}")
    print("═" * width)
    for cat, entries in leaderboard.items():
        print(f"\n  📊  {cat}")
        print("  " + "─" * (width - 2))
        if not entries:
            print("      No data yet.")
            continue
        for i, entry in enumerate(entries, start=1):
            bar_len = int(entry["fame_delta"] / max(entries[0]["fame_delta"], 1) * 20)
            bar = "█" * bar_len
            print(f"  {i}.  {entry['player_name']:<20}  {entry['fame_delta']:>12,}  {bar}")
    print()
    print("═" * width)
    print()


# ════════════════════════════════════════════════════════════════
# DIAGNOSTICS
# ════════════════════════════════════════════════════════════════

def print_diagnostics(conn: sqlite3.Connection) -> None:
    """Print a short database health summary."""
    print("\n  📋  DATABASE DIAGNOSTICS")
    print("  " + "─" * 50)

    row = conn.execute("SELECT COUNT(*) AS c, MIN(snapshot_date) AS first, MAX(snapshot_date) AS last FROM snapshots").fetchone()
    print(f"  Snapshots      : {row['c']} rows  ({row['first']} → {row['last']})")

    row = conn.execute("SELECT COUNT(*) AS c, MIN(stat_date) AS first, MAX(stat_date) AS last FROM daily_deltas").fetchone()
    print(f"  Daily deltas   : {row['c']} rows  ({row['first']} → {row['last']})")

    row = conn.execute("SELECT COUNT(*) AS c FROM leaderboard").fetchone()
    print(f"  Leaderboard    : {row['c']} rows")

    row = conn.execute("SELECT COUNT(*) AS c FROM run_log WHERE status = 'ok'").fetchone()
    print(f"  Successful runs: {row['c']}")

    row = conn.execute("SELECT COUNT(*) AS c FROM run_log WHERE status = 'error'").fetchone()
    print(f"  Failed runs    : {row['c']}")

    print(f"  DB file        : {DB_PATH.resolve()}")
    print()


def log_run(conn: sqlite3.Connection, status: str, members: int | None,
            delta_computed: int, message: str = "") -> None:
    conn.execute("""
        INSERT INTO run_log (run_at, status, members_fetched, delta_computed, message)
        VALUES (?,?,?,?,?)
    """, (datetime.now(timezone.utc).isoformat(), status, members, delta_computed, message))
    conn.commit()


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main() -> None:
    today = (date.today() - timedelta(days=1)).isoformat()       # e.g. "2026-06-04"
    log.info("=== Albion Guild Stats — %s ===", today)

    conn = get_connection()
    init_db(conn)

    # 1. Fetch live data
    try:
        members = fetch_members()
    except Exception as exc:
        log.error("API fetch failed: %s", exc)
        log_run(conn, "error", None, 0, str(exc))
        conn.close()
        sys.exit(1)

    # 2. Save snapshot
    save_snapshot(conn, members, today)

    # 3. Find previous snapshot
    prev_date = get_previous_snapshot_date(conn, today)

    if prev_date is None:
        log.info("No previous snapshot found — this is the first run. "
                 "Come back tomorrow for a daily delta!")
        log_run(conn, "first_run", len(members), 0,
                "First snapshot saved. Delta will be available tomorrow.")
        print_diagnostics(conn)
        conn.close()
        return

    log.info("Computing delta: %s  →  %s", prev_date, today)

    # 4. Compute deltas
    today_snap = load_snapshot_dict(conn, today)
    prev_snap  = load_snapshot_dict(conn, prev_date)
    deltas     = compute_deltas(today_snap, prev_snap, today)
    save_deltas(conn, deltas)

    # 5. Build & save leaderboard
    leaderboard = build_leaderboard(conn, today)
    # Enrich leaderboard entries with player_id for the save step
    for cat, col in CATEGORY_COL.items():
        rows = conn.execute(f"""
            SELECT player_id, player_name, {col} AS fame_delta
            FROM daily_deltas WHERE stat_date = ?
            ORDER BY {col} DESC LIMIT ?
        """, (today, TOP_N)).fetchall()
        leaderboard[cat] = [dict(r) for r in rows]

    save_leaderboard(conn, today, leaderboard)

    # 6. Print report
    print_report(today, leaderboard)

    # 7. Diagnostics
    print_diagnostics(conn)

    # 8. Log success
    log_run(conn, "ok", len(members), 1)
    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()