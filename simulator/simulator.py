"""
simulator.py — Main entry point for the Mini Twitter async user simulator.

Usage:
    cd simulator
    pip install -r requirements.txt
    python simulator.py                    # uses config.yaml in same dir
    python simulator.py --config my.yaml   # custom config path

What it does:
    1. Loads configuration from config.yaml
    2. Verifies backend health
    3. Ramps up N simulated users (register → login → action loop)
    4. Prints a live dashboard every few seconds
    5. Waits for all users to finish
    6. Prints a final summary with all metrics
"""

import sys
import os
import json
import time
import asyncio
import argparse
import logging
from pathlib import Path

import yaml
import httpx

from metrics import SimulatorMetrics
from api_client import MiniTwitterClient
from user_agent import UserAgent, SharedPools

# ──────────── Logging setup ────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulator")


# ──────────── Dashboard printer (no rich dependency required) ────────────

def clear_screen() -> None:
    """Clear terminal screen cross-platform."""
    os.system("cls" if os.name == "nt" else "clear")


async def print_dashboard(metrics: SimulatorMetrics, interval: float) -> None:
    """
    Periodically print a live stats dashboard to the terminal.
    Runs as a background task until cancelled.
    """
    try:
        # Try importing rich for a prettier dashboard
        from rich.console import Console
        from rich.table import Table
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text
        use_rich = True
    except ImportError:
        use_rich = False

    if use_rich:
        await _dashboard_rich(metrics, interval)
    else:
        await _dashboard_plain(metrics, interval)


async def _dashboard_rich(metrics: SimulatorMetrics, interval: float) -> None:
    """Rich-powered live dashboard."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text

    console = Console()

    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            snap = await metrics.snapshot()

            # ── Header panel ──
            success_pct = (
                f"{snap['success'] / snap['total'] * 100:.1f}%"
                if snap["total"] > 0 else "N/A"
            )
            header = Text()
            header.append("Mini Twitter Simulator", style="bold cyan")
            header.append(f"\n\nUptime: {snap['elapsed_s']}s", style="white")
            header.append(f"   Active Users: {snap['active_users']}/{snap['peak_users']}", style="green")
            header.append(f"   RPS: {snap['rps']}", style="yellow")
            header.append(f"\nTotal: {snap['total']}", style="white")
            header.append(f"   Success: {snap['success']} ({success_pct})", style="green")
            header.append(f"   Failed: {snap['fail']}", style="red" if snap["fail"] > 0 else "white")
            header.append(
                f"\nLatency — Avg: {snap['avg_ms']}ms"
                f"   Min: {snap['min_ms']}ms"
                f"   Max: {snap['max_ms']}ms"
                f"   P95: {snap['p95_ms']}ms",
                style="white",
            )

            # ── Per-endpoint table ──
            table = Table(title="Per-Endpoint Breakdown", show_lines=True)
            table.add_column("Endpoint", style="cyan", min_width=16)
            table.add_column("Count", justify="right")
            table.add_column("Fail", justify="right", style="red")
            table.add_column("Avg ms", justify="right")
            table.add_column("Max ms", justify="right")

            for name, ep in snap["per_endpoint"].items():
                table.add_row(
                    name,
                    str(ep["count"]),
                    str(ep["fail"]),
                    str(ep["avg_ms"]),
                    str(ep["max_ms"]),
                )

            # ── Errors ──
            error_text = ""
            if snap["recent_errors"]:
                error_text = "\n".join(snap["recent_errors"])
            else:
                error_text = "No errors"

            # Combine
            from rich.columns import Columns
            from rich.console import Group

            output = Group(
                Panel(header, title="[bold]Dashboard[/bold]", border_style="blue"),
                table,
                Panel(error_text, title="Recent Errors", border_style="red"),
            )
            live.update(output)

            await asyncio.sleep(interval)


async def _dashboard_plain(metrics: SimulatorMetrics, interval: float) -> None:
    """Fallback plain-text dashboard when rich is not installed."""
    while True:
        snap = await metrics.snapshot()
        success_pct = (
            f"{snap['success'] / snap['total'] * 100:.1f}%"
            if snap["total"] > 0 else "N/A"
        )

        lines = [
            "",
            "=" * 65,
            "       MINI TWITTER SIMULATOR — LIVE DASHBOARD",
            "=" * 65,
            f"  Uptime: {snap['elapsed_s']}s    "
            f"Active Users: {snap['active_users']}/{snap['peak_users']}    "
            f"RPS: {snap['rps']}",
            f"  Total: {snap['total']}    "
            f"Success: {snap['success']} ({success_pct})    "
            f"Failed: {snap['fail']}",
            f"  Latency — Avg: {snap['avg_ms']}ms    "
            f"Min: {snap['min_ms']}ms    "
            f"Max: {snap['max_ms']}ms    "
            f"P95: {snap['p95_ms']}ms",
            "-" * 65,
            f"  {'Endpoint':<18} {'Count':>6} {'Fail':>6} {'Avg ms':>8} {'Max ms':>8}",
            "-" * 65,
        ]

        for name, ep in snap["per_endpoint"].items():
            lines.append(
                f"  {name:<18} {ep['count']:>6} {ep['fail']:>6} "
                f"{ep['avg_ms']:>8} {ep['max_ms']:>8}"
            )

        lines.append("-" * 65)
        if snap["recent_errors"]:
            lines.append("  Recent Errors:")
            for err in snap["recent_errors"]:
                lines.append(f"    {err}")
        else:
            lines.append("  No errors")
        lines.append("=" * 65)

        clear_screen()
        print("\n".join(lines))

        await asyncio.sleep(interval)


# ──────────── Final summary ────────────

async def print_final_summary(metrics: SimulatorMetrics) -> None:
    """Print the comprehensive end-of-run summary."""
    summary = await metrics.final_summary()

    success_pct = (
        f"{summary['success'] / summary['total'] * 100:.1f}%"
        if summary["total"] > 0 else "N/A"
    )

    print("\n")
    print("=" * 70)
    print("             SIMULATION COMPLETE — FINAL SUMMARY")
    print("=" * 70)
    print(f"  Duration:       {summary['elapsed_s']}s")
    print(f"  Total Requests: {summary['total']}")
    print(f"  RPS:            {summary['rps']}")
    print(f"  Success:        {summary['success']} ({success_pct})")
    print(f"  Failed:         {summary['fail']}")
    print(f"  Peak Users:     {summary['peak_users']}")
    print()
    print(f"  Latency:")
    print(f"    Average:      {summary['avg_ms']} ms")
    print(f"    Min:          {summary['min_ms']} ms")
    print(f"    Max:          {summary['max_ms']} ms")
    print(f"    P95:          {summary['p95_ms']} ms")
    print()

    # Per-endpoint breakdown
    print("-" * 70)
    print(f"  {'Endpoint':<18} {'Count':>7} {'Fail':>6} {'Avg ms':>9} {'Max ms':>9}")
    print("-" * 70)
    for name, ep in summary["per_endpoint"].items():
        print(
            f"  {name:<18} {ep['count']:>7} {ep['fail']:>6} "
            f"{ep['avg_ms']:>9} {ep['max_ms']:>9}"
        )

    # Top 10 slowest
    if summary.get("top_slowest"):
        print()
        print(f"  Top 10 Slowest Requests (ms): {summary['top_slowest']}")

    # Error summary by type
    if summary.get("error_types"):
        print()
        print("  Error Breakdown:")
        for etype, count in summary["error_types"].items():
            print(f"    {etype}: {count} occurrences")

    print("=" * 70)

    # Dump full error log to file
    errors_list = summary.get("total_errors_list", [])
    if errors_list:
        errors_path = Path(__file__).parent / "errors.json"
        with open(errors_path, "w") as f:
            json.dump(errors_list, f, indent=2)
        print(f"\n  Full error log written to: {errors_path}")
        print(f"  Total errors logged: {len(errors_list)}")
    print()


# ──────────── Main orchestrator ────────────

async def main(config_path: str) -> None:
    """
    Main simulation flow:
      1. Load config
      2. Health check
      3. Ramp up users (register + login, staggered)
      4. Run all users concurrently with live dashboard
      5. Print final summary
    """

    # ── 1. Load config ──
    config_file = Path(config_path)
    if not config_file.exists():
        logger.error("Config file not found: %s", config_file)
        sys.exit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    base_url = config["server"]["base_url"]
    num_users = config["simulation"]["num_users"]
    ramp_up = config["simulation"]["ramp_up_seconds"]
    stats_interval = config["monitoring"]["stats_interval_seconds"]

    logger.info("Loaded config from %s", config_file)
    logger.info("Target: %s | Users: %d | Actions/user: %d",
                base_url, num_users, config["simulation"]["actions_per_user"])

    # ── 2. Create shared state ──
    metrics = SimulatorMetrics()
    pools = SharedPools()

    # ── 3. Health check ──
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    timeout = httpx.Timeout(30.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as session:
        health_client = MiniTwitterClient(session, base_url, metrics, "healthcheck")
        status, data, latency = await health_client.health()
        if status != 200:
            logger.error(
                "Backend health check failed (status=%d). Is the backend running at %s?",
                status, base_url,
            )
            logger.error("Start the backend with: docker compose up --build")
            sys.exit(1)
        logger.info("Backend healthy: %s (%.0fms)", data, latency)

        # ── 4. Create user agents ──
        agents: list[UserAgent] = []
        for i in range(num_users):
            client = MiniTwitterClient(session, base_url, metrics)
            agent = UserAgent(i, client, pools, config)
            agents.append(agent)

        # ── 5. Launch dashboard + users ──
        dashboard_task = asyncio.create_task(
            print_dashboard(metrics, stats_interval)
        )

        # Staggered ramp-up
        user_tasks: list[asyncio.Task] = []
        ramp_delay = ramp_up / max(num_users, 1)

        logger.info("Ramping up %d users over %ds (%.2fs apart)...",
                     num_users, ramp_up, ramp_delay)

        for agent in agents:
            task = asyncio.create_task(agent.run())
            user_tasks.append(task)
            await asyncio.sleep(ramp_delay)

        # ── 6. Wait for all users to complete ──
        await asyncio.gather(*user_tasks, return_exceptions=True)

        # ── 7. Stop dashboard and print summary ──
        dashboard_task.cancel()
        try:
            await dashboard_task
        except asyncio.CancelledError:
            pass

    await print_final_summary(metrics)


# ──────────── CLI entry point ────────────

def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Mini Twitter Async User Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulator.py                      # Use config.yaml in current dir
  python simulator.py --config prod.yaml   # Use custom config

Backend must be running:
  cd .. && docker compose up --build
        """,
    )
    parser.add_argument(
        "--config", "-c",
        default=str(Path(__file__).parent / "config.yaml"),
        help="Path to YAML configuration file (default: config.yaml)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.config))
    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    cli()
