# Cache Proxy Systemd Service Setup - Auto-Start Configuration

## Metadata
- **Created**: 2025-02-18
- **Project**: sglang-embedding-cache
- **Component**: cache_proxy
- **Tags**: systemd, service, conda, uvicorn, auto-start, linux
- **Related Gists**: None yet

## Summary

Created a complete systemd service configuration for automatically starting the embedding cache proxy on system boot. The setup includes a bash startup script that activates the conda environment and a systemd service unit that manages the process lifecycle with automatic restart on failure. This enables the cache proxy to run as a background service with proper dependency management, centralized logging, and automatic recovery.

## Problem Statement

The embedding cache proxy needed to be configured as a system service that:
- Starts automatically on boot
- Depends on the sglang-embedding service being available
- Uses the correct conda environment (`sglang-embedding-cache`)
- Provides proper logging via systemd journal
- Automatically restarts on failure

The user requested: "I've created the Linux service files for auto-starting the cache proxy on boot" and wanted to document the setup for future reference.

## Environment
- **OS**: Linux 6.8
- **Shell**: /bin/bash
- **User**: vvek
- **Working Directory**: `/home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache`
- **Conda Environment**: sglang-embedding-cache
- **Cache Proxy Port**: 8081
- **Dependency Service**: `sgl.emb.octen-0.6b.fp16.service`
- **Miniconda Path**: `/home/vvek/miniconda3`
- **Constraints**: Must use conda environment, must start after network and embedding service

## Timeline
- **2025-02-18 ~05:05 UTC**: User reported completion of service file creation
- **2025-02-18 ~05:07 UTC**: Initial gist created with basic structure
- **2025-02-18 ~05:11 UTC**: User requested enhancement of gistify skill with review step
- **2025-02-18 ~05:12 UTC**: Enhanced gistify skill updated with comprehensive checklists
- **2025-02-18 ~05:13 UTC**: Regenerating gist with enhanced structure

## Thought Process

### Initial Analysis

The task was straightforward: document the systemd service setup that was already created. However, the user's request to enhance the gistify skill revealed a deeper need - creating a knowledge base that could be stitched together chronologically to provide context for future work.

### Design Decisions

**1. Two-file architecture**
- **Why**: Separation of concerns - bash script handles environment activation, systemd handles process management
- **Alternative considered**: Single systemd unit with `EnvironmentFile` - rejected because conda activation requires sourcing shell scripts, which systemd doesn't handle natively

**2. Using `exec` for uvicorn**
- **Why**: Critical for signal propagation. Without `exec`, SIGTERM would be received by bash but not forwarded to uvicorn, causing unclean shutdowns
- **Learning**: This is a common pitfall when wrapping processes in bash scripts for systemd

**3. `Wants=` vs `Requires=` for dependency**
- **Why**: `Wants` allows the cache proxy to start even if the embedding service fails, while `Requires` would prevent startup entirely
- **Rationale**: Better to have a degraded service than no service at all

**4. `Restart=on-failure` with `RestartSec=10s`**
- **Why**: Automatic recovery with delay prevents rapid restart loops (restart storms)
- **Learning**: 10 seconds is a reasonable default - long enough to prevent loops, short enough for quick recovery

**5. Logging to systemd journal**
- **Why**: Centralized logging is easier to manage than separate log files
- **Benefit**: Can use `journalctl -u cache-proxy` for filtering, `-f` for tailing, `-n` for recent entries

### No Dead Ends

This was a straightforward implementation with no failed approaches or dead ends. The design was informed by prior experience with systemd and conda integration.

## Solution

Created two files:

### 1. Startup Script: `cache_proxy/start-cache-proxy.sh`

```bash
#!/bin/bash
# Start script for cache proxy service
# This script activates the conda environment and starts the cache proxy

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate sglang-embedding-cache

# Change to cache_proxy directory
cd "$PROJECT_DIR/cache_proxy"

# Start the cache proxy
echo "Starting cache proxy service..."
exec uvicorn main:app --host 0.0.0.0 --port 8081
```

### 2. Systemd Service Unit: `cache-proxy.service`

```ini
[Unit]
Description=Embedding Cache Proxy Service
After=network.target
Wants=sgl.emb.octen-0.6b.fp16.service

[Service]
Type=simple
User=vvek
WorkingDirectory=/home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache
Environment="PATH=/home/vvek/miniconda3/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache/cache_proxy/start-cache-proxy.sh
Restart=on-failure
RestartSec=10s

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cache-proxy

[Install]
WantedBy=multi-user.target
```

## Changes Made

### New Files Created

| File | Purpose | Key Features |
|------|---------|--------------|
| `cache_proxy/start-cache-proxy.sh` | Startup script | Conda activation, error handling with `set -e`, `exec` for signal propagation, relative path resolution |
| `cache-proxy.service` | Systemd unit | Dependency management, auto-restart, journal logging, explicit PATH configuration |

### Installation Commands Required

```bash
# Copy service file to systemd directory
sudo cp cache-proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cache-proxy.service
sudo systemctl start cache-proxy.service
```

### Testing Commands

```bash
# Test the startup script manually
./cache_proxy/start-cache-proxy.sh

# Check service status
systemctl status cache-proxy

# View logs in real-time
journalctl -u cache-proxy -f

# View recent logs
journalctl -u cache-proxy -n 50

# View logs since boot
journalctl -u cache-proxy -b
```

### Service Management Commands

```bash
# Stop the service
sudo systemctl stop cache-proxy

# Restart the service
sudo systemctl restart cache-proxy

# Disable auto-start on boot
sudo systemctl disable cache-proxy

# View service configuration
systemctl cat cache-proxy

# Check service dependencies
systemctl list-dependencies cache-proxy
```

## Learnings

### Technical Insights

1. **Conda with Systemd**: Systemd doesn't natively handle conda environments. The solution is to use a bash wrapper script that sources the conda initialization and activates the environment before starting the service. This is a common pattern for Python services using conda.

2. **Signal Propagation**: Using `exec` to run uvicorn is critical. Without `exec`, signals (like SIGTERM for graceful shutdown) would be received by the bash script but not forwarded to the uvicorn process, causing unclean shutdowns. This is a subtle but important detail that can cause issues during service restarts or system shutdowns.

3. **Dependency Management**: Using `Wants=` instead of `Requires=` for the sglang service is a deliberate choice. `Wants` allows the cache proxy to start even if the dependency fails, while `Requires` would prevent the cache proxy from starting at all if the dependency isn't available. This provides better resilience.

4. **Path Configuration**: Explicitly setting `PATH` in the service unit ensures the conda binaries are available, even though the startup script also activates conda. This is defensive programming - the PATH is set in both places to ensure it's available regardless of which code path is taken.

5. **Working Directory**: Setting `WorkingDirectory` in the service unit ensures relative paths in the application work correctly, even though the script also changes directories. Again, this is defensive - both the service unit and the script set the working directory.

6. **Error Handling**: The `set -e` directive in the bash script ensures that any command failure causes the script to exit immediately. This prevents the service from starting in a partially-initialized state.

### Process Learnings

1. **Documentation Value**: Creating comprehensive documentation immediately after completing a task is valuable. The details are fresh in mind, and the documentation serves as a reference for future work.

2. **Knowledge Base Approach**: Using a consistent structure for documentation (like the gistify skill) enables building a chronological knowledge base. Each document can be stitched together to provide context for future work.

3. **Review Checklist**: Having a comprehensive review checklist ensures that important details aren't missed. The "future-self check" is particularly valuable - asking "If I read this a month from now, would I understand what happened and why?"

### Edge Cases and Considerations

1. **Conda Path Hardcoding**: The script uses `~/miniconda3` which is hardcoded. This works for the current setup but would need to be adjusted if conda is installed in a different location.

2. **User Account**: The service runs as user `vvek`. For production deployments, consider creating a dedicated system user with minimal privileges.

3. **Port Binding**: The service binds to `0.0.0.0:8081`, making it accessible from all network interfaces. For security, consider binding to a specific interface or using a firewall.

4. **No Health Check**: The service doesn't include a health check. Adding `ExecStartPost` with a curl command could verify the service is actually responding.

### Potential Improvements

1. **Environment Variables**: Consider adding a `.env` file loader in the startup script for configuration flexibility. This would allow changing settings without modifying the script.

2. **Health Checks**: Add `ExecStartPost` with a health check to verify the service is actually responding:
   ```ini
   ExecStartPost=/bin/sleep 5
   ExecStartPost=/usr/bin/curl -f http://localhost:8081/health || /bin/false
   ```

3. **Resource Limits**: Add `MemoryLimit` and `CPUQuota` to prevent resource exhaustion:
   ```ini
   MemoryLimit=2G
   CPUQuota=200%
   ```

4. **User/Group**: Consider creating a dedicated system user for running the service instead of using a personal user account.

5. **Log Rotation**: While systemd journal handles log rotation, consider configuring `journald` settings if the service produces a lot of logs.

6. **Watchdog**: Add `WatchdogSec` and implement a watchdog endpoint in the application for automatic restart on hangs.

## Open Questions / Follow-up Items

1. **Service Installation**: The service files have been created but not yet installed to `/etc/systemd/system/`. This needs to be done manually with the installation commands.

2. **Testing**: The service should be tested after installation to ensure it starts correctly and the dependency on `sgl.emb.octen-0.6b.fp16.service` works as expected.

3. **Gradio Service**: Consider creating a similar systemd service for the `gradio_code_search` component for consistency.

4. **Monitoring**: Consider setting up monitoring/alerting for the service status and logs.

## References

### External Documentation
- [systemd.service(5) - Linux man page](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Conda Integration with systemd](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)
- [uvicorn deployment documentation](https://www.uvicorn.org/deployment/)
- [systemd journalctl usage](https://www.freedesktop.org/software/systemd/man/journalctl.html)
- [systemd.exec(5) - Environment variables in systemd](https://www.freedesktop.org/software/systemd/man/systemd.exec.html)

### Related Project Files
- [`cache_proxy/main.py`](cache_proxy/main.py) - The FastAPI application that the service runs
- [`cache_proxy/config.py`](cache_proxy/config.py) - Configuration settings for the cache proxy
- [`readme.md`](readme.md) - Project documentation
- [`.env`](.env) - Environment variables (not committed to git)

### Related Gists in This Project
- None yet - this is the first gist in the knowledge base

---

**Document Version**: 1.0
**Last Updated**: 2025-02-18
**Status**: Complete (service files created, pending installation and testing)
