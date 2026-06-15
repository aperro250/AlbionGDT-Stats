"""
Albion Guild Stats — Daily Controller
======================================
Orchestrates the full daily pipeline:

  Step 1 — Rebuild config.json from environment variables
            (used in CI/GitHub Actions where secrets are env vars)
  Step 2 — Run main.py  → fetch API, compute deltas, store leaderboard in DB
  Step 3 — Run discord_bot.py --post-daily → post the leaderboard to Discord

Usage
-----
  Normal (local, config.json already present):
      python run_daily.py

  CI / GitHub Actions (secrets injected as env vars):
      DISCORD_TOKEN=xxx ALBION_GUILD_ID=yyy DISCORD_CHANNEL_IDS=zzz python run_daily.py

Environment variables (all optional when config.json is already populated):
  DISCORD_TOKEN           Bot token
  ALBION_GUILD_ID         Albion Online guild ID
  DISCORD_CHANNEL_IDS     Comma-separated list of Discord channel IDs for 'rating'
                          e.g.  "1284230734155874398,9876543210000000001"

Exit codes
----------
  0  — Everything succeeded
  1  — main.py failed (stats not collected; Discord post skipped)
  2  — Discord post failed
  3  — Config rebuild failed
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SNAPSHOOT_PY     = BASE_DIR / "Take_Snapshoot.py"
BOT_PY      = BASE_DIR / "discord_bot.py"
PYTHON      = sys.executable          # same interpreter that launched this script

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("controller")


# ════════════════════════════════════════════════════════════════
# STEP 0 — CONFIG BOOTSTRAP
# ════════════════════════════════════════════════════════════════

def _default_config() -> dict:
    return {
        "discord_token": "",
        "guild_id": "",
        "channels": {"rating": []},
    }


def rebuild_config_from_env() -> None:
    """
    If environment variables are present, write/overwrite config.json with them.
    This allows GitHub Actions secrets to be the single source of truth in CI.
    """
    token      = os.environ.get("DISCORD_TOKEN", "").strip()
    guild_id   = os.environ.get("ALBION_GUILD_ID", "").strip()
    ch_raw     = os.environ.get("DISCORD_CHANNEL_IDS", "").strip()

    # Nothing in env → rely on existing config.json
    if not any([token, guild_id, ch_raw]):
        log.info("No CI env vars detected — using existing config.json")
        return

    # Parse comma-separated channel IDs
    channel_ids: list[int] = []
    for part in ch_raw.split(","):
        part = part.strip()
        if part.isdigit():
            channel_ids.append(int(part))
        elif part:
            log.warning("Skipping non-numeric channel ID: %r", part)

    # Load existing config (or start fresh) and overlay env values
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as fh:
            cfg = json.load(fh)
    else:
        cfg = _default_config()

    if token:
        cfg["discord_token"] = token
    if guild_id:
        cfg["guild_id"] = guild_id
    if channel_ids:
        cfg.setdefault("channels", {})["rating"] = channel_ids

    with CONFIG_PATH.open("w") as fh:
        json.dump(cfg, fh, indent=4)

    log.info(
        "Config rebuilt from env vars  |  guild=%s  channels=%s",
        cfg.get("guild_id"),
        cfg.get("channels", {}).get("rating"),
    )


def validate_config() -> bool:
    """Return True only if the config has the minimum required fields."""
    if not CONFIG_PATH.exists():
        log.error("config.json not found at %s", CONFIG_PATH.resolve())
        return False

    with CONFIG_PATH.open() as fh:
        cfg = json.load(fh)

    ok = True
    if not cfg.get("discord_token"):
        log.error("config.json: 'discord_token' is empty")
        ok = False
    if not cfg.get("guild_id"):
        log.warning("config.json: 'guild_id' is empty — main.py may use its own hardcoded value")
    if not cfg.get("channels", {}).get("rating"):
        log.warning("config.json: no 'rating' channels registered — Discord post will be a no-op")

    return ok


# ════════════════════════════════════════════════════════════════
# STEP RUNNER
# ════════════════════════════════════════════════════════════════

def run_step(label: str, cmd: list[str], exit_on_fail: int) -> bool:
    """
    Run a subprocess step.  Streams output live.
    Returns True on success, exits with `exit_on_fail` on failure.
    """
    log.info("━━━  %s  ━━━", label)
    log.info("Command: %s", " ".join(cmd))

    result = subprocess.run(cmd, cwd=BASE_DIR)

    if result.returncode != 0:
        log.error("%s FAILED (exit code %d)", label, result.returncode)
        sys.exit(exit_on_fail)

    log.info("%s completed successfully.", label)
    return True


# ════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ════════════════════════════════════════════════════════════════

def main() -> None:
    log.info("╔══════════════════════════════════════════╗")
    log.info("║   Albion Guild Stats — Daily Controller  ║")
    log.info("╚══════════════════════════════════════════╝")

    # ── Step 0: Bootstrap config from env (CI) ─────────────────
    try:
        rebuild_config_from_env()
    except Exception as exc:
        log.error("Config bootstrap failed: %s", exc)
        sys.exit(3)

    if not validate_config():
        sys.exit(3)

    # ── Step 1: Collect stats ───────────────────────────────────
    run_step(
        label       = "STEP 1 — Fetch & store daily stats (main.py)",
        cmd         = [PYTHON, str(SNAPSHOOT_PY)],
        exit_on_fail= 1,
    )

    # ── Step 2: Post to Discord ─────────────────────────────────
    run_step(
        label       = "STEP 2 — Post leaderboard to Discord",
        cmd         = [PYTHON, str(BOT_PY), "--post-daily"],
        exit_on_fail= 2,
    )

    log.info("╔══════════════════════════════════════════╗")
    log.info("║   Pipeline finished successfully ✓       ║")
    log.info("╚══════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
