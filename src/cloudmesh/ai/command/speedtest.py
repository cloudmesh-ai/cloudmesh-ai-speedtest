"""
Cloudmesh AI Speedtest Extension
================================

This extension provides tools to measure network throughput to remote hosts
and predict the time required to transfer local directories based on
historical data.

It supports multiple transfer protocols:
- SCP (Secure Copy)
- SFTP (SSH File Transfer Protocol)
- Rsync (Remote Sync)

Usage Examples:
-------------------------------------------------------------------------------
1. Run a speed test to a host using default SCP (50MB test):
   $ cme speedtest run my-server.com

2. Run a speed test using SFTP with a specific file size (100MB):
   $ cme speedtest run my-server.com --copy=sftp --size=100

3. Run a speed test using Rsync with a specific SSH user:
   $ cme speedtest run my-server.com --copy=rsync --user=admin

4. Predict how long it will take to upload a folder based on previous SCP tests:
   $ cme speedtest predict my-server.com --path=/home/user/data --copy=scp

Sample Output (run):
-------------------------------------------------------------------------------
┌────────────────────────────────────────────────────────────────────────────┐
│                          Speedtest Results: my-server.com (SCP)            │
├──────────────────┬─────────────────────────────────────────────────────────┤
│ Metric           │ Value                                                   │
├──────────────────┼─────────────────────────────────────────────────────────┤
│ Method           │ SCP                                                     │
│ Sample Size      │ 50 MB                                                   │
│ Throughput       │ 125.50 MB/s (1004.00 Mbps)                               │
│ Projected 1GB    │ 8.16s (8s)                                              │
└──────────────────┴─────────────────────────────────────────────────────────┘

Sample Output (predict):
-------------------------------------------------------------------------------
┌────────────────────────────────────────────────────────────────────────────┐
│                      Transfer Prediction for my-server.com (SCP)           │
├──────────────────┬─────────────────────────────────────────────────────────┤
│ Parameter        │ Value                                                   │
├──────────────────┼─────────────────────────────────────────────────────────┤
│ Source Path      │ /home/user/data                                         │
│ Total Size       │ 1024.00 MB                                              │
│ Stored Speed     │ 125.50 MB/s                                             │
│ Estimated Time   │ 8.16s (8s)                                              │
└──────────────────┴─────────────────────────────────────────────────────────┘

Usage:
    speedtest run <host> [options]
    speedtest predict <host> --path <path> [options]
    speedtest -h | --help

Arguments:
    <host>             Remote host to test or predict for.
    <path>             Local path to analyze for size prediction.

Options:
    --size <mb>        Size of test file to generate in MB (default: 50).
    --user <user>      SSH username to use.
    --copy <method>    Protocol to use (scp, sftp, rsync).
    -h, --help         Show this screen.
-------------------------------------------------------------------------------
"""

import os
import json
import math
import subprocess
import shutil
import click
import time
from datetime import datetime
from pathlib import Path

from cloudmesh.ai.common.stopwatch import StopWatch
from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.common.io import path_expand
from cloudmesh.ai.common.sys import systeminfo
from cloudmesh.ai.common.telemetry import Telemetry

# Import Rich components for the table
from rich.console import Console
from rich.table import Table
from rich import box

# Initialize Rich console
console = Console()

# Initialize Logger
logger = get_logger("speedtest")

# Initialize Telemetry
telemetry = Telemetry("speedtest")

# --- Helpers ---


def load_config():
    """Loads the general AI configuration file."""
    config_path = Path(path_expand("~/.config/cloudmesh/ai/config.json"))
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_history_path():
    """Returns the path to the speedtest history file based on config."""
    config = load_config()
    # Use filename from config if available, otherwise default to speedtest.json
    filename = config.get("speedtest_history", "speedtest.json")
    
    # Ensure the file is placed in the standard AI config directory
    base_dir = "~/.config/cloudmesh/ai/"
    path_str = path_expand(f"{base_dir}{filename}")
    
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_path_size_mb(path_str):
    """Calculates total size of a file or directory in Megabytes."""
    p = Path(path_str).expanduser().resolve()
    if not p.exists():
        return 0
    if p.is_file():
        size_bytes = p.stat().st_size
    else:
        size_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return size_bytes / (1024 * 1024)


def format_hms(total_seconds):
    """Formats seconds into rounded-up H M S string."""
    total_s_rounded = math.ceil(total_seconds)
    h = total_s_rounded // 3600
    m = (total_s_rounded % 3600) // 60
    s = total_s_rounded % 60
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0 or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def generate_fast_dummy_file(path, size_mb):
    """Generates a dummy file quickly using a repeated buffer."""
    chunk = os.urandom(1024 * 1024)  # 1MB chunk
    with open(path, "wb") as f:
        for _ in range(size_mb):
            f.write(chunk)


# --- Click Group and Commands ---


@click.group()
def speedtest_group():
    """
    Speedtest tool for measuring and predicting SSH transfer speeds.

    This group contains commands to benchmark current network performance
    and predict future transfer times using cached speed history.
    """
    pass

@speedtest_group.command(name="internet")
@click.option("-y", "--yes", is_flag=True, help="Automatically answer yes to the confirmation prompt.")
def internet_cmd(yes):
    """
    Conduct an internet speed test using the Ookla speedtest CLI.
    """
    if shutil.which("speedtest") is None:
        click.secho("\nError: Ookla speedtest CLI is not installed.", fg="red")
        click.echo("\nTo install it, run the following commands:")
        click.echo("--------------------------------------------------")
        click.echo("brew tap teamookla/speedtest")
        click.echo("brew update")
        click.echo("# brew uninstall speedtest --force")
        click.echo("# brew uninstall speedtest-cli --force")
        click.echo("brew install speedtest --force")
        click.echo("--------------------------------------------------")
        click.echo("\nFor more information, visit: https://www.speedtest.net/apps/cli")
        return

    if yes or click.confirm("\nWould you like to conduct the speedtest with the Ookla program?", default=False):
        try:
            # Run speedtest and stream output to console
            result = subprocess.run(["speedtest"], capture_output=False, text=True)
            if result.returncode != 0:
                click.secho(f"\nSpeedtest failed with exit code {result.returncode}", fg="red")
        except Exception as e:
            click.secho(f"\nAn error occurred while running speedtest: {e}", fg="red")
    else:
        click.echo("\nSpeedtest cancelled.")


@speedtest_group.command(name="run")  # Changed from 'ssh' to 'run'
@click.argument("host")
@click.option(
    "--size", default=50, type=int, help="Size of test file to generate in MB."
)
@click.option("--user", type=str, help="SSH username to use (overrides ~/.ssh/config).")
@click.option(
    "--copy",
    "copy_method",
    type=click.Choice(["scp", "sftp", "rsync"], case_sensitive=False),
    default="scp",
    help="The protocol to use for the transfer test.",
)
def run_cmd(host, size, user, copy_method):
    """
    Benchmark the transfer speed to a remote host.

    This command generates a dummy file of the specified size, transfers it to
    the remote /tmp directory using the chosen protocol, and calculates the
    effective throughput. The result is saved to the local history file.

    Example:
        cme speedtest run 192.168.1.10 --copy=rsync --size=100
    """
    
    target = f"{user}@{host}" if user else host
    test_file = Path("speedtest_dummy.bin")
    remote_path = f"/tmp/{test_file.name}"

    ssh_opts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]

    try:
        try:
            telemetry.start(message=f"Running speedtest to {host} via {copy_method}")
        except Exception as te:
            logger.debug(f"Telemetry start failed: {te}")

        logger.info(f"Generating {size}MB test data...")
        generate_fast_dummy_file(test_file, size)

        logger.info(f"Transferring to {host} via {copy_method}...")

        if copy_method == "scp":
            cmd = ["scp"] + ssh_opts + [str(test_file), f"{target}:{remote_path}"]
        elif copy_method == "rsync":
            ssh_cmd_str = f"ssh {' '.join(ssh_opts)}"
            cmd = [
                "rsync",
                "-aq",
                "-e",
                ssh_cmd_str,
                str(test_file),
                f"{target}:{remote_path}",
            ]
        elif copy_method == "sftp":
            batch_file = Path("sftp_batch.txt")
            batch_file.write_text(f"put {test_file} {remote_path}\nquit\n")
            cmd = ["sftp"] + ssh_opts + ["-b", str(batch_file), target]

        StopWatch.start("transfer")
        start_time_iso = datetime.now().isoformat()

        subprocess.run(cmd, check=True, capture_output=True, text=True)

        StopWatch.stop("transfer")
        duration = StopWatch.get("transfer")
        
        # Guard against division by zero in fast/mocked environments
        safe_duration = max(duration, 0.0001)
        speed_mbytes = size / safe_duration
        speed_mbits = (size * 8) / safe_duration
        proj_1gb_total_seconds = 1024 / speed_mbytes
        time_breakdown = format_hms(proj_1gb_total_seconds)

        # Record telemetry
        try:
            telemetry.complete(metrics={
                "speed_mbytes": speed_mbytes,
                "speed_mbits": speed_mbits,
                "duration": duration,
                "size_mb": size,
                "host": host,
                "method": copy_method
            })
        except Exception as te:
            logger.debug(f"Telemetry complete failed: {te}")

        history_file = get_history_path()
        history = {}
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        history_key = f"{host}:{copy_method}"
        # Ensure systeminfo is JSON serializable by converting values to strings
        sys_info = systeminfo()
        serializable_sys_info = {k: str(v) for k, v in sys_info.items()} if sys_info else {}

        history[history_key] = {
            "speed_mbytes": speed_mbytes,
            "target_full": target,
            "method": copy_method,
            "timestamp": start_time_iso,
            "system": serializable_sys_info,
        }
        with open(history_file, "w") as f:
            json.dump(history, f, indent=4)

        table = Table(
            title=f"Speedtest Results: {host} ({copy_method})",
            show_header=True,
            header_style="bold magenta",
            box=box.ROUNDED,
        )
        table.add_column("Metric", style="blue")
        table.add_column("Value", style="black")

        table.add_row("Method", copy_method.upper())
        table.add_row("Sample Size", f"{size} MB")
        table.add_row("Throughput", f"{speed_mbytes:.2f} MB/s ({speed_mbits:.2f} Mbps)")
        table.add_row(
            "Projected 1GB", f"{proj_1gb_total_seconds:.2f}s ({time_breakdown})"
        )

        console.print("\n", table)

        subprocess.run(
            ["ssh"] + ssh_opts + [target, f"rm {remote_path}"],
            check=True,
            capture_output=True,
        )

        if copy_method == "sftp" and Path("sftp_batch.txt").exists():
            Path("sftp_batch.txt").unlink()

    except Exception as e:
        try:
            telemetry.fail(error=str(e))
        except Exception as te:
            logger.debug(f"Telemetry fail failed: {te}")
        click.secho(f"Execution failed: {e}", fg="red")
    finally:
        if test_file.exists():
            test_file.unlink()


@speedtest_group.command(name="predict")
@click.argument("host")
@click.option(
    "--path", required=True, type=click.Path(exists=True), help="Local path to analyze."
)
@click.option(
    "--copy",
    "copy_method",
    type=click.Choice(["scp", "sftp", "rsync"], case_sensitive=False),
    default="scp",
    help="The recorded protocol to use for the speed calculation.",
)
def predict_cmd(host, path, copy_method):
    """
    Predict transfer time for a local path based on historical speed.

    Calculates the total size of the provided path (files and subdirectories)
    and divides it by the most recent speed recorded for that specific
    host and protocol combination.

    Example:
        cme speedtest predict my-server.com --path=./my_project --copy=sftp
    """
    history_file = get_history_path()
    if not history_file.exists():
        click.secho(f"No history found. Run 'speedtest run HOST' first.", fg="yellow")
        return

    with open(history_file, "r") as f:
        history = json.load(f)

    history_key = f"{host}:{copy_method}"
    if history_key not in history:
        click.secho(
            f"No recorded speed for '{host}' using {copy_method} in history.",
            fg="yellow",
        )
        return

    speed_mbytes = history[history_key]["speed_mbytes"]
    total_mb = get_path_size_mb(path)

    if total_mb == 0:
        click.secho(f"Path '{path}' is empty.", fg="yellow")
        return

    total_seconds = total_mb / speed_mbytes
    time_display = format_hms(total_seconds)

    table = Table(
        title=f"Transfer Prediction for {host} ({copy_method})",
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
    )
    table.add_column("Parameter", style="blue")
    table.add_column("Value", style="black")

    table.add_row("Source Path", str(path))
    table.add_row("Total Size", f"{total_mb:.2f} MB")
    table.add_row("Stored Speed", f"{speed_mbytes:.2f} MB/s")
    table.add_row("Estimated Time", f"{total_seconds:.2f}s ({time_display})")

    console.print("\n", table)


entry_point = speedtest_group

def register(cli):
    cli.add_command(speedtest_group, name="speedtest")
