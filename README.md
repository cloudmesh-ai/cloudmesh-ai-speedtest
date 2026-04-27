# Cloudmesh AI Speedtest Extension

This extension provides tools to measure network throughput to remote hosts
and predict the time required to transfer local directories based on
historical data.

It supports multiple transfer protocols:
- SCP (Secure Copy)
- SFTP (SSH File Transfer Protocol)
- Rsync (Remote Sync)

## Installation

### Recommended: Using pipx
For the best experience with CLI tools, use `pipx` to install `cloudmesh-ai-speedtest` in an isolated environment.

``` bash
pipx install cloudmesh-ai-speedtest
```

To install from a local directory:
``` bash
pipx install .
```

### Using pip
If you prefer a standard installation in your current environment:

``` bash
pip install cloudmesh-ai-speedtest
```

To install from a local directory:
``` bash
pip install .
```

## Usage Examples

1. Run a speed test to a host using default SCP (50MB test):
   `cme speedtest run my-server.com`

2. Run a speed test using SFTP with a specific file size (100MB):
   `cme speedtest run my-server.com --copy=sftp --size=100`

3. Run a speed test using Rsync with a specific SSH user:
   `cme speedtest run my-server.com --copy=rsync --user=admin`

4. Predict how long it will take to upload a folder based on previous SCP tests:
   `cme speedtest predict my-server.com --path=/home/user/data --copy=scp`

5. Test internet speed using Ookla Speedtest CLI:
   `cme speedtest internet`

## Installation of Ookla Speedtest CLI

To use the `speedtest internet` command, you must have the Ookla speedtest CLI installed:

```bash
brew tap teamookla/speedtest
brew update
# Example how to remove conflicting or old versions using brew
# brew uninstall speedtest --force
# brew uninstall speedtest-cli --force
brew install speedtest --force
```

For more information, visit: https://www.speedtest.net/apps/cli