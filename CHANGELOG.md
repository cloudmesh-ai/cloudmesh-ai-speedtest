# Changelog

All notable changes to `cloudmesh-ai-speedtest` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0.2.dev1] - 2026-04-19

### Added
- **SSH Speedtest Command**: Introduced the `speedtest` command to measure actual data transfer rates over SSH.
- **Transfer Prediction**: Added logic to predict the time required to transfer large AI models and datasets based on measured speeds.
- **Performance Benchmarking**: Implemented utilities to benchmark network throughput between DGX hosts and other endpoints.
- **Test Suite**: Added unit and integration tests in `tests/test_speedtest.py` to ensure accuracy of speed measurements.
- **Version Management**: Integrated `version_mgmt.py` for consistent versioning across the extension.

### Changed
- Initial project structure established as a specialized extension for the `cloudmesh-ai` ecosystem.