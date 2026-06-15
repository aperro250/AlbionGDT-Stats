"""
Albion Online Guild Stats — Discord Bot
========================================
Reads daily leaderboard data from the SQLite database produced by main.py
and posts formatted reports to configured Discord channels.

Features
--------
  /set-channel rating        — Register the current channel to receive "rating" reports
  /set-guild-id <GUILD_ID>   — Store the Albion guild ID in the config file
  /send-daily-stats          — Immediately post the latest leaderboard to all
                               registered "rating" channels

Configuration (config.json)
---------------------------
{
    "discord_token": "YOUR_BOT_TOKEN_HERE",
    "guild_id": "",
    "channels": {
        "rating": []          ← list of Discord channel IDs (int)
    }
}

Setup
-----
    pip install discord.py
    python discord_bot.py

Schedule the daily post with cron (e.g. just after main.py finishes at 23:59):
    59 23 * * * /usr/bin/python3 /path/to/discord_bot.py --post-daily
"""

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from pathlib import Path

import discord
from discord import app_commands

# ──────────────────────────────────────────────
# PATHS & CONSTANTS
# ──────────────────────────────────────────────
CONFIG_PATH = Path("config.json")
DB_PATH     = Path("albion_guild_stats.db")
TOP_N       = 5
# Medal emojis for ranks 1-5; falls back to a number for higher ranks
MEDALS = {1: "1.", 2: "2.", 3: "3.", 4: "4.", 5: "5."}

# Category metadata: display label + column name in daily_deltas + emoji
CATEGORIES = [
    ("Kill Fame",      "kill_fame_delta",      "⚔️"),
    ("Death Fame",     "death_fame_delta",      "💀"),
    ("PvE Fame",       "pve_fame_delta",        "🐉"),
    ("Gathering Fame", "gathering_fame_delta",  "🌿"),
    ("Crafting Fame",  "crafting_fame_delta",   "🔨"),
]

# Supported channel types (expandable in the future)
CHANNEL_TYPES = ["rating"]

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# CONFIG HELPERS
# ════════════════════════════════════════════════════════════════

def _default_config() -> dict:
    return {
        "discord_token": "",
        "guild_id": "",
        "channels": {t: [] for t in CHANNEL_TYPES},
    }


def load_config() -> dict:
    """Load config.json, creating it with defaults if absent."""
    if not CONFIG_PATH.exists():
        cfg = _default_config()
        save_config(cfg)
        log.info("Created default config at %s", CONFIG_PATH.resolve())
    else:
        with CONFIG_PATH.open() as fh:
            cfg = json.load(fh)
        # Ensure all channel keys exist (forward-compat)
        cfg.setdefault("channels", {})
        for t in CHANNEL_TYPES:
            cfg["channels"].setdefault(t, [])
    return cfg


def save_config(cfg: dict) -> None:
    with CONFIG_PATH.open("w") as fh:
        json.dump(cfg, fh, indent=4)
    log.info("Config saved to %s", CONFIG_PATH.resolve())


# ════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ════════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_latest_leaderboard() -> tuple[str | None, dict[str, list[dict]]]:
    """
    Return (stat_date, leaderboard) for the most recent date in the
    leaderboard table.  leaderboard = {category: [{player_name, fame_delta, rank}]}
    """
    if not DB_PATH.exists():
        return None, {}

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT stat_date FROM leaderboard ORDER BY stat_date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None, {}

        stat_date = row["stat_date"]
        leaderboard: dict[str, list[dict]] = {}

        for cat_name, col, _emoji in CATEGORIES:
            rows = conn.execute(
                """
                SELECT rank, player_name, fame_delta
                FROM   leaderboard
                WHERE  stat_date = ? AND category = ?
                ORDER  BY rank
                """,
                (stat_date, cat_name),
            ).fetchall()
            leaderboard[cat_name] = [dict(r) for r in rows]

        return stat_date, leaderboard
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════
# DISCORD EMBED BUILDER
# ════════════════════════════════════════════════════════════════

def _fmt_number(n: int) -> str:
    """Format large numbers with k/M suffixes for compact display."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _bar(value: int, maximum: int, width: int = 10) -> str:
    """Return a compact Unicode block bar relative to the maximum value."""
    if maximum <= 0:
        return "░" * width
    filled = round(value / maximum * width)
    return "█" * filled + "░" * (width - filled)


def build_embeds(stat_date: str, leaderboard: dict[str, list[dict]]) -> list[discord.Embed]:
    """
    Build a list of Discord Embeds — one header embed + one per category.
    Keeping them separate avoids the 6 000-character embed limit.
    """
    embeds: list[discord.Embed] = []

    # ── Header embed ──────────────────────────────────────────────
    header = discord.Embed(
        title="🏆  Albion Guild — Daily Fame Report",
        description=f"**Date:** {stat_date}",
        color=discord.Color.gold(),
    )
    header.set_footer(text="Stats computed from daily snapshots · Albion Online")
    embeds.append(header)

    # ── One embed per category ────────────────────────────────────
    cat_colors = [
        discord.Color.red(),
        discord.Color.dark_grey(),
        discord.Color.green(),
        discord.Color.teal(),
        discord.Color.orange(),
    ]

    for idx, (cat_name, _col, emoji) in enumerate(CATEGORIES):
        entries = leaderboard.get(cat_name, [])
        embed = discord.Embed(
            title=f"{emoji}  {cat_name}",
            color=cat_colors[idx % len(cat_colors)],
        )

        if not entries:
            embed.description = "_No data available for this date._"
            embeds.append(embed)
            continue

        top_value = entries[0]["fame_delta"] if entries else 1

        # Build a code-block table for clean alignment
        lines = ["```"]
        lines.append(f"{'#':<3}  {'Player':<20}  {'Fame':>8}  {'':10}")
        lines.append("─" * 46)

        for entry in entries:
            rank     = entry["rank"]
            name     = entry["player_name"][:20]          # truncate very long names
            fame     = entry["fame_delta"]
            medal    = MEDALS.get(rank, f"{rank}.")
            bar      = _bar(fame, top_value, width=10)
            fame_str = _fmt_number(fame)
            lines.append(f"{medal}  {name:<20}  {fame_str:>8}  {bar}")

        lines.append("```")
        embed.description = "\n".join(lines)
        embeds.append(embed)

    return embeds


# ════════════════════════════════════════════════════════════════
# BOT
# ════════════════════════════════════════════════════════════════

class AlbionBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Sync slash commands globally (can take up to an hour to propagate)
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)


client = AlbionBot()


# ════════════════════════════════════════════════════════════════
# SLASH COMMANDS
# ════════════════════════════════════════════════════════════════

@client.tree.command(
    name="set-channel",
    description="Register this channel to receive a specific type of report.",
)
@app_commands.describe(report_type="Type of report to send to this channel (e.g. rating)")
@app_commands.choices(
    report_type=[app_commands.Choice(name=t, value=t) for t in CHANNEL_TYPES]
)
@app_commands.checks.has_permissions(manage_channels=True)
async def set_channel(interaction: discord.Interaction, report_type: app_commands.Choice[str]) -> None:
    """Register the current channel for a chosen report type."""
    cfg = load_config()
    channel_id = interaction.channel_id
    key = report_type.value

    channel_list: list = cfg["channels"].setdefault(key, [])
    if channel_id in channel_list:
        await interaction.response.send_message(
            f"✅ This channel is **already** registered for `{key}` reports.",
            ephemeral=True,
        )
        return

    channel_list.append(channel_id)
    save_config(cfg)
    log.info("Channel %s registered for '%s' reports.", channel_id, key)
    await interaction.response.send_message(
        f"✅ This channel has been registered to receive **{key}** reports!",
        ephemeral=True,
    )


@client.tree.command(
    name="set-guild-id",
    description="Store the Albion Online Guild ID in the bot configuration.",
)
@app_commands.describe(guild_id="Your Albion Online guild ID (from the Albion API)")
@app_commands.checks.has_permissions(administrator=True)
async def set_guild_id(interaction: discord.Interaction, guild_id: str) -> None:
    """Persist the Albion guild ID to config.json."""
    cfg = load_config()
    cfg["guild_id"] = guild_id.strip()
    save_config(cfg)
    log.info("Guild ID set to '%s'.", guild_id)
    await interaction.response.send_message(
        f"✅ Albion guild ID has been set to `{guild_id}`.",
        ephemeral=True,
    )


@client.tree.command(
    name="send-daily-stats",
    description="Post the latest daily fame leaderboard to all registered rating channels.",
)
@app_commands.checks.has_permissions(manage_channels=True)
async def send_daily_stats(interaction: discord.Interaction) -> None:
    """Manually trigger posting of the daily stats to all registered channels."""
    await interaction.response.defer(ephemeral=True)

    stat_date, leaderboard = fetch_latest_leaderboard()
    if stat_date is None:
        await interaction.followup.send(
            "⚠️ No leaderboard data found in the database. "
            "Make sure `main.py` has been run at least twice.",
            ephemeral=True,
        )
        return

    count = await post_to_channels(stat_date, leaderboard)
    await interaction.followup.send(
        f"✅ Daily stats for **{stat_date}** posted to **{count}** channel(s).",
        ephemeral=True,
    )


# ════════════════════════════════════════════════════════════════
# POSTING HELPER (shared by command + scheduled/CLI post)
# ════════════════════════════════════════════════════════════════

async def post_to_channels(stat_date: str, leaderboard: dict) -> int:
    """
    Send the formatted leaderboard embeds to every channel registered under
    the 'rating' key.  Returns the number of channels successfully posted to.
    """
    cfg = load_config()
    channel_ids: list[int] = cfg["channels"].get("rating", [])

    if not channel_ids:
        log.warning("No channels registered for 'rating'. Use /set-channel rating first.")
        return 0

    embeds = build_embeds(stat_date, leaderboard)
    success = 0

    for ch_id in channel_ids:
        try:
            # fetch_channel() makes a direct API call — no cache needed.
            # This is safe in both headless (--post-daily) and interactive mode.
            channel = await client.fetch_channel(ch_id)
        except discord.NotFound:
            log.error("Channel %s does not exist or was deleted.", ch_id)
            continue
        except discord.Forbidden:
            log.error("Channel %s: bot lacks permission to access it.", ch_id)
            continue
        except discord.HTTPException as exc:
            log.error("Channel %s: failed to fetch (%s).", ch_id, exc)
            continue
        try:
            # Discord allows up to 10 embeds per message
            for i in range(0, len(embeds), 10):
                await channel.send(embeds=embeds[i:i + 10])
            log.info("Posted stats to channel %s", ch_id)
            success += 1
        except discord.Forbidden:
            log.error("Channel %s: bot lacks permission to send messages.", ch_id)
        except discord.HTTPException as exc:
            log.error("Failed to post to channel %s: %s", ch_id, exc)

    return success


# ════════════════════════════════════════════════════════════════
# ERROR HANDLER
# ════════════════════════════════════════════════════════════════

@client.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "🚫 You don't have permission to use this command.", ephemeral=True
        )
    else:
        log.error("Unhandled command error: %s", error)
        await interaction.response.send_message(
            "❌ An unexpected error occurred.", ephemeral=True
        )


# ════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ════════════════════════════════════════════════════════════════

async def _post_daily_and_exit() -> None:
    """
    Headless mode: connect to Discord, post stats to all channels, then quit.
    Designed to be called from cron right after main.py finishes.
    """
    stat_date, leaderboard = fetch_latest_leaderboard()
    if stat_date is None:
        log.error("No leaderboard data found. Aborting.")
        return

    cfg = load_config()
    token = cfg.get("discord_token", "")
    if not token:
        log.error("discord_token is empty in config.json. Aborting.")
        return

    async with client:
        await client.login(token)
        # fetch_channel() uses the REST API directly — no gateway/cache needed.
        count = await post_to_channels(stat_date, leaderboard)
        log.info("Headless post complete. Sent to %d channel(s).", count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Albion Guild Stats Discord Bot")
    parser.add_argument(
        "--post-daily",
        action="store_true",
        help="Post the latest daily stats to all registered channels and exit "
             "(no interactive bot; suitable for cron).",
    )
    args = parser.parse_args()

    cfg = load_config()
    token = cfg.get("discord_token", "")
    if not token:
        log.error(
            "discord_token is missing or empty in %s.\n"
            "Edit the file and paste your bot token, then re-run.",
            CONFIG_PATH.resolve(),
        )
        sys.exit(1)

    if args.post_daily:
        asyncio.run(_post_daily_and_exit())
    else:
        log.info("Starting Albion Guild Stats bot…")
        client.run(token)


if __name__ == "__main__":
    main()