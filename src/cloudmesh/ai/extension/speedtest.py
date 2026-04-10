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
-------------------------------------------------------------------------------
"""

import os
import json
import math
import subprocess
import click
import time
from datetime import datetime
from pathlib import Path

# Import Rich components for the table
from rich.console import Console
from rich.table import Table
from rich import box

# Initialize Rich console
console = Console()

# --- Helpers ---


def get_history_path():
    """Returns the path to the speedtest history file."""
    path = Path("~/.config/cloudmesh/ai/speedtest.json").expanduser()
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
        click.echo(f"Generating {size}MB test data...")
        generate_fast_dummy_file(test_file, size)

        click.echo(f"Transferring to {host} via {copy_method}...")

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

        start_time_perf = time.perf_counter()
        start_time_iso = datetime.now().isoformat()

        subprocess.run(cmd, check=True, capture_output=True, text=True)

        duration = time.perf_counter() - start_time_perf
        speed_mbytes = size / duration
        speed_mbits = (size * 8) / duration
        proj_1gb_total_seconds = 1024 / speed_mbytes
        time_breakdown = format_hms(proj_1gb_total_seconds)

        history_file = get_history_path()
        history = {}
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        history_key = f"{host}:{copy_method}"
        history[history_key] = {
            "speed_mbytes": speed_mbytes,
            "target_full": target,
            "method": copy_method,
            "timestamp": start_time_iso,
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


def register(cli):
    cli.add_command(speedtest_group, name="speedtest")
