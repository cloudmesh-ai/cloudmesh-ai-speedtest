import os
import json
import math
import subprocess
import click
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


# --- Click Group and Commands ---


@click.group()
def speedtest_group():
    """Speedtest tool for measuring and predicting SSH transfer speeds."""
    pass


@speedtest_group.command(name="ssh")
@click.argument("host")
@click.option("--size", default=50, type=int, help="Size of test file in MB.")
@click.option("--user", type=str, help="SSH username (overrides ~/.ssh/config).")
def ssh_cmd(host, size, user):
    """Test transfer speed to a remote host via SCP."""
    target = f"{user}@{host}" if user else host
    test_file = Path("speedtest_dummy.bin")
    remote_path = f"/tmp/{test_file.name}"

    try:
        click.echo(f"Generating {size}MB random data file...")
        with open(test_file, "wb") as f:
            f.write(os.urandom(size * 1024 * 1024))

        click.echo(f"Transferring to {host} via SCP...")

        import time

        start_time_perf = time.perf_counter()
        start_time_iso = datetime.now().isoformat()

        subprocess.run(
            ["scp", str(test_file), f"{target}:{remote_path}"],
            check=True,
            capture_output=True,
            text=True,
        )

        duration = time.perf_counter() - start_time_perf

        # Calculations
        speed_mbytes = size / duration
        speed_mbits = (size * 8) / duration
        proj_1gb_total_seconds = 1024 / speed_mbytes
        time_breakdown = format_hms(proj_1gb_total_seconds)

        # Save to history
        history_file = get_history_path()
        history = {}
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        history[host] = {
            "speed_mbytes": speed_mbytes,
            "target_full": target,
            "timestamp": start_time_iso,
        }
        with open(history_file, "w") as f:
            json.dump(history, f, indent=4)

        # --- RICH TABLE FOR RESULTS ---
        table = Table(
            title=f"Speedtest Results: {host}",
            show_header=True,
            header_style="bold magenta",
            box=box.ROUNDED,
        )
        table.add_column("Metric", style="blue")
        table.add_column("Value", style="black")

        table.add_row("Sample Size", f"{size} MB")
        table.add_row("Throughput", f"{speed_mbytes:.2f} MB/s ({speed_mbits:.2f} Mbps)")
        table.add_row(
            "Projected 1GB", f"{proj_1gb_total_seconds:.2f}s ({time_breakdown})"
        )

        console.print("\n", table)

        # Cleanup remote file
        subprocess.run(
            ["ssh", target, f"rm {remote_path}"], check=True, capture_output=True
        )

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
def predict_cmd(host, path):
    """Predict transfer time for a path based on recorded speed."""
    history_file = get_history_path()
    if not history_file.exists():
        click.secho(f"No history found. Run 'speedtest ssh HOST' first.", fg="yellow")
        return

    with open(history_file, "r") as f:
        history = json.load(f)

    if host not in history:
        click.secho(f"No recorded speed for '{host}' in history.", fg="yellow")
        return

    speed_mbytes = history[host]["speed_mbytes"]
    total_mb = get_path_size_mb(path)

    if total_mb == 0:
        click.secho(f"Path '{path}' is empty.", fg="yellow")
        return

    total_seconds = total_mb / speed_mbytes
    time_display = format_hms(total_seconds)

    # --- RICH TABLE FOR PREDICTION ---
    table = Table(
        title=f"Transfer Prediction for {host}",
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


# --- Registration ---


def register(cli):
    """
    This function is called by cme-core's load_core_extensions()
    because this file is located in the cloudmesh.ai.extension namespace.
    """
    cli.add_command(speedtest_group, name="speedtest")
