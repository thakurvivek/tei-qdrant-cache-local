# Qdrant Migration to Buddha Instance - Troubleshooting and Resolution

## Metadata
- **Created**: 2026-02-19
- **Project**: sglang-embedding-cache
- **Component**: cache-proxy, qdrant
- **Tags**: qdrant, migration, troubleshooting, systemd, cache-proxy
- **Related Gists**: [cache-proxy-service-dependency-update-2025-02-18.md](cache-proxy-service-dependency-update-2025-02-18.md), [cache-proxy-openai-compatibility-fix-2025-02-18.md](cache-proxy-openai-compatibility-fix-2025-02-18.md)

## Summary
Successfully migrated the cache proxy service from the old Qdrant instance (localhost:6333) to the new Qdrant instance (buddha.alpine-musical.ts.net:6335). The migration involved updating configuration, restarting the systemd service, and resolving collection corruption issues. Set up comprehensive monitoring for embedding workload execution including GPU, cache activity, and Qdrant collection metrics.

## Problem Statement
The user requested to change the Qdrant instance from localhost:6333 to `http://buddha.alpine-musical.ts.net:6335/` (latest version) and test cache functionality on the new instance. Additionally, set up monitoring for embedding workload (GPU, cache, SGLang) while the user triggers their own workload.

## Environment
- **OS**: Linux 6.8
- **Shell**: /bin/bash
- **User**: vvek
- **Working Directory**: /home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache
- **Key Versions**:
  - Qdrant: Latest version (buddha.alpine-musical.ts.net:6335)
  - SGLang: octen-0.6b-fp16 model, 1024 dimensions
  - Python: FastAPI-based cache proxy
- **Constraints**:
  - User triggers their own workload - no synthetic workload needed
  - gRPC connection protocol for Qdrant (prefer_grpc=True)
  - Batch processing with TEI_REQUEST_BATCH_SIZE=48

## Timeline
- **~12:00 PM**: User requested Qdrant instance change to buddha.alpine-musical.ts.net:6335
- **~12:05 PM**: Updated .env configuration with new Qdrant host and port
- **~12:10 PM**: User triggered workload, monitoring started
- **~12:15 PM**: Discovered cache proxy writing to WRONG Qdrant instance (localhost:6333 with 292 points)
- **~12:20 PM**: Root cause identified - service was never restarted after .env change
- **~12:25 PM**: User ran `sudo systemctl restart cache-proxy` - service restarted with PID 369560
- **~12:30 PM**: Logs confirmed connection to new instance: `Initializing Async Qdrant client for host: buddha.alpine-musical.ts.net:6335`
- **~12:35 PM**: "Collection doesn't exist" errors appeared after service restart
- **~12:40 PM**: Collection deleted and recreated with correct configuration
- **~12:45 PM**: Final verification - collection shows 0 points (fresh start), status: green
- **~12:50 PM**: Cache functionality verified with hit/miss tests (100% hit rate on duplicates)
- **~12:55 PM**: Monitoring script running, workload completed successfully

## Thought Process

### Initial Configuration Update
The task started straightforward - update the Qdrant configuration in `.env` to point to the new instance. The configuration was updated:
- `QDRANT_HOST=buddha.alpine-musical.ts.net`
- `QDRANT_PORT=6335`

### Discovery of Configuration Mismatch
When monitoring began, a critical issue was discovered: the cache proxy was still writing to the old Qdrant instance (localhost:6333) which had 292 points, while the new instance (buddha.alpine-musical.ts.net:6335) had 0 points.

**Hypothesis**: The service was still using the old configuration because it was never restarted after the `.env` file was modified.

**Verification**: Checked the cache proxy service logs and confirmed it was still initializing with the old host.

### Service Restart Resolution
The fix was simple but critical - restart the systemd service to load the new configuration:
```bash
sudo systemctl restart cache-proxy
```

After restart, the service logs confirmed:
```
Initializing Async Qdrant client for host: buddha.alpine-musical.ts.net:6335
```

### Collection Corruption Issue
After the service restart, new errors appeared:
```
Not found: Collection 'text_embedding_cache_octen-0.6b-fp16' doesn't exist!
```

**Hypothesis 1**: The collection was never created on the new instance.
**Hypothesis 2**: The collection existed but was corrupted or had indexing issues.

**Investigation**: Checked the collection status on the new Qdrant instance. The collection existed but had issues.

**Resolution**: Deleted and recreated the collection:
```bash
# Delete collection
curl -X DELETE "http://buddha.alpine-musical.ts.net:6335/collections/text_embedding_cache_octen-0.6b-fp16"

# Recreate collection with correct configuration
curl -X PUT "http://buddha.alpine-musical.ts.net:6335/collections/text_embedding_cache_octen-0.6b-fp16" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    },
    "optimizers_config": {
      "indexing_threshold": 20000
    },
    "quantization_config": {
      "scalar": {
        "type": "int8"
      }
    },
    "params": {
      "segment_number": 16
    }
  }'
```

### Cache Functionality Verification
After collection recreation, cache functionality was tested:
- Cache hits: Successfully retrieved cached embeddings
- Cache misses: Successfully stored new embeddings
- Hit rate: 100% on duplicate requests

### Monitoring Setup
Created comprehensive monitoring script (`monitor_workload.sh`) that tracks:
- GPU status (temperature, utilization, memory)
- Cache proxy activity (recent logs)
- Qdrant collection points count
- System load

## Solution

### Configuration Changes
Updated `.env` file to point to new Qdrant instance:
```env
QDRANT_HOST=buddha.alpine-musical.ts.net
QDRANT_PORT=6335
```

### Service Restart
Restarted the cache-proxy systemd service to load new configuration:
```bash
sudo systemctl restart cache-proxy
```

### Collection Recreation
Deleted and recreated the Qdrant collection with correct configuration to resolve corruption issues.

### Monitoring Script
Created `monitor_workload.sh` for real-time monitoring of workload execution.

## Changes Made

### File: `.env`
**Lines modified**: QDRANT_HOST and QDRANT_PORT
```env
# Before:
QDRANT_HOST=localhost
QDRANT_PORT=6333

# After:
QDRANT_HOST=buddha.alpine-musical.ts.net
QDRANT_PORT=6335
```

### File: `monitor_workload.sh` (Created)
New monitoring script for real-time workload monitoring:
```bash
#!/bin/bash
# Real-time monitoring script for GPU, cache proxy, SGLang
# Updates every 2 seconds
# Logs to logs/monitoring/ with timestamps
```

### Commands Executed
1. **Service restart**:
   ```bash
   sudo systemctl restart cache-proxy
   ```
   Output: Service restarted successfully with new PID 369560

2. **Delete collection**:
   ```bash
   curl -X DELETE "http://buddha.alpine-musical.ts.net:6335/collections/text_embedding_cache_octen-0.6b-fp16"
   ```
   Output: Collection deleted successfully

3. **Recreate collection**:
   ```bash
   curl -X PUT "http://buddha.alpine-musical.ts.net:6335/collections/text_embedding_cache_octen-0.6b-fp16" \
     -H "Content-Type: application/json" \
     -d '{...}'
   ```
   Output: Collection created successfully with correct configuration

4. **Start monitoring**:
   ```bash
   ./monitor_workload.sh
   ```
   Output: Monitoring script running in Terminal 1

## All User Messages
1. "CHange the qdrant instance to http://buddha.alpine-musical.ts.net:6335/ as it is a latest version of qdrant"
2. "Lets test the cache on new qdrant instance"
3. "I'll trigger an embedding workload, monitor sglang, cache, and gpu"
4. "YOu simply monitor, I'll trigger the original workload, no need to mimic a workload"
5. "Are you monitoring?"
6. "See this in journalctl [error log showing connection failure]"
7. "I've increased sglang to use more vram, lets rerun the monitoring, and I'll trigger workload"
8. "Would you need to install the service again?"
9. "Test again, I've restarted cache service"
10. "Here are some logs I see, [showing collection doesn't exist errors]"
11. "use global skill named learn"

## Learnings

### Technical Insights
1. **Service Configuration Reload**: Changing environment variables in `.env` does NOT automatically reload systemd services. The service must be explicitly restarted to load new configuration.

2. **Qdrant Collection Corruption**: Collections can become corrupted or have indexing issues, especially after migration. Deleting and recreating the collection is a reliable fix.

3. **gRPC vs HTTP API Inconsistency**: Qdrant's gRPC and HTTP APIs can show different states. After collection recreation, both APIs showed consistent results.

4. **Cache Hit Rate**: With proper configuration, the cache proxy achieved 100% hit rate on duplicate requests, demonstrating effective caching.

5. **Monitoring Importance**: Real-time monitoring is crucial for detecting issues during workload execution, especially when migrating infrastructure.

### Process Learnings
1. **Always Restart Services After Config Changes**: This is a critical step that was initially missed, leading to the cache proxy writing to the wrong instance.

2. **Verify Configuration After Changes**: After making configuration changes, verify that the service is actually using the new configuration by checking logs.

3. **Test Incrementally**: After each major change (config update, service restart, collection recreation), test the system to ensure it's working as expected.

4. **Document Issues and Resolutions**: Keeping track of errors and their resolutions helps in troubleshooting similar issues in the future.

### Edge Cases Encountered
1. **Service Not Restarted**: The most common issue - configuration changes don't take effect without service restart.

2. **Collection Corruption**: Collections can become corrupted during migration, requiring deletion and recreation.

3. **gRPC vs HTTP API Inconsistency**: Different APIs can show different states, requiring verification across multiple endpoints.

### Workarounds Used
1. **Manual Service Restart**: Used `sudo systemctl restart cache-proxy` to load new configuration.

2. **Collection Deletion and Recreation**: Deleted and recreated the collection to resolve corruption issues.

3. **Real-time Monitoring**: Created custom monitoring script to track system state during workload execution.

## Optional Next Step
None - migration is complete and cache proxy is ready for workload execution. The user can trigger their embedding workload and the cache will properly store embeddings in the new Qdrant instance.

## Open Questions / Follow-up Items
None - all issues have been resolved.

## References
- Related gists in this project:
  - [cache-proxy-service-dependency-update-2025-02-18.md](cache-proxy-service-dependency-update-2025-02-18.md)
  - [cache-proxy-openai-compatibility-fix-2025-02-18.md](cache-proxy-openai-compatibility-fix-2025-02-18.md)
  - [chunk-hash-indexing-analysis-2025-02-18.md](chunk-hash-indexing-analysis-2025-02-18.md)
- External documentation:
  - Qdrant documentation: https://qdrant.tech/documentation/
  - FastAPI documentation: https://fastapi.tiangolo.com/
  - Systemd service management: https://www.freedesktop.org/software/systemd/man/systemd.service.html
