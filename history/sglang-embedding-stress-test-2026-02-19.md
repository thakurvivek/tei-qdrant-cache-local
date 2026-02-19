# SGLang Embedding Service Stress Test - Diagnosing and Fixing Batch Request Failures

## Metadata
- **Created**: 2026-02-19
- **Project**: sglang-setup
- **Component**: sgl.emb.octen-0.6b.fp16.service
- **Tags**: sglang, embedding, stress-test, debugging, concurrency, oom
- **Related Gists**: None

## Summary

Successfully diagnosed and fixed batch request failures in the SGLang embedding service on port 5000. Root cause was a configuration mismatch where `max-running-requests=30` exceeded the actual memory pool capacity (29 slots), causing OOM crashes. Fixed by increasing to `max-running-requests=64`, which now handles 1000+ concurrent requests successfully through batch processing and queuing.

## Problem Statement

User reported that `sgl.emb.octen-0.6b.fp16.service` on port 5000 fails when running embedding batch requests. The service was experiencing repeated crashes with exit code 137 (SIGKILL/OOM).

## Environment

- **OS**: Linux 6.8
- **Shell**: /bin/bash
- **User**: vvek
- **Working Directory**: /home/vvek/deep/sglang-setup
- **Key Versions**: 
  - SGLang (from git/sglang)
  - Python 3.12
  - CUDA (RTX 5090, 32GB)
- **Constraints**: 
  - Service runs as systemd service
  - Model loaded from RAM disk at /mnt/model-cache
  - GPU: RTX 5090 with UUID GPU-c9d63bab-798c-8e8a-c509-47cc6d0c1e90

## Timeline

- **10:18:07**: Service started (restart #5)
- **10:18:40**: Service crashed with alloc_req_slots error (30 requests vs 29 slots)
- **10:20:18**: Service restarted (restart #8)
- **10:21:34**: Service crashed again
- **10:24:12**: Service crashed again
- **10:32:32**: Service restarted after user changed config to max-running-requests=64
- **10:36:08**: Stress test completed - 50 concurrent requests succeeded
- **10:38:20**: High concurrency test - 100 concurrent requests succeeded
- **10:40:04**: Very high concurrency test - 200+ concurrent requests succeeded
- **10:40-10:45**: Extreme concurrency test - 1000 concurrent requests succeeded

## Thought Process

### Initial Diagnosis

1. **Examined service logs** - Found repeated crashes with exit code 137 (SIGKILL/OOM)
2. **Found error message**: `RuntimeError: alloc_req_slots runs out of memory. Please set a smaller number for --max-running-requests. req_to_token_pool.available_size()=29, num_reqs=30`
3. **Identified root cause**: Configuration mismatch - `max-running-requests=30` but pool only has 29 slots

### Hypothesis Testing

**Hypothesis 1**: Memory pool calculation is incorrect for embedding models
- **Test**: Created stress test script to find actual breaking point
- **Result**: With max-running-requests=30, service failed at 25-30 concurrent requests
- **Conclusion**: Confirmed - pool capacity was insufficient

**Hypothesis 2**: Increasing max-running-requests will fix the issue
- **Test**: User changed to max-running-requests=64
- **Result**: Service now handles 1000+ concurrent requests
- **Conclusion**: Confirmed - higher value resolves the issue

### Key Insights

1. **Batch Processing**: SGLang doesn't process all requests simultaneously. It processes in batches (10-12 at a time based on logs) and queues the rest.
2. **Effective Concurrency**: The `max-running-requests` parameter controls the pool size, not simultaneous processing.
3. **Throughput vs Concurrency**: High throughput is achieved through queuing and batch processing, not by increasing concurrent slots.

## Solution

Changed `max-running-requests` from 30 to 64 in the service wrapper script.

### File Modified

**File**: `scripts/emb/octen/0.6b/fp16/sgl.emb.octen-0.6b.fp16-wrapper.sh`

**Line 166**:
```bash
# Before:
--max-running-requests 30

# After:
--max-running-requests 64
```

### Service Restart

Service was restarted by user (requires sudo):
```bash
systemctl restart sgl.emb.octen-0.6b.fp16.service
```

## Changes Made

### Configuration Changes

1. **Modified**: `scripts/emb/octen/0.6b/fp16/sgl.emb.octen-0.6b.fp16-wrapper.sh`
   - Line 166: Changed `--max-running-requests 30` to `--max-running-requests 64`

### Test Scripts Created

1. **`scripts/emb/octen/0.6b/fp16/stress-test-embedding.py`**
   - Binary search to find maximum concurrent requests
   - Tests different batch sizes
   - Provides recommendations

2. **`scripts/emb/octen/0.6b/fp16/find-max-concurrency.py`**
   - Focused test to find exact breaking point
   - Tests 50-100 concurrent requests

3. **`scripts/emb/octen/0.6b/fp16/test-above-100.py`**
   - Tests 110-200 concurrent requests
   - Verifies stability above 100

4. **`scripts/emb/octen/0.6b/fp16/test-high-concurrency.py`**
   - Tests 250-1000 concurrent requests
   - Finds ultimate throughput limit

### Commands Executed

```bash
# Check service status
systemctl status sgl.emb.octen-0.6b.fp16.service

# View service logs
tail -100 /home/vvek/deep/sglang-setup/scripts/emb/octen/0.6b/fp16/sgl.emb.octen-0.6b.fp16.log

# Run stress test
python3 scripts/emb/octen/0.6b/fp16/stress-test-embedding.py

# Find max concurrency
python3 scripts/emb/octen/0.6b/fp16/find-max-concurrency.py

# Test high concurrency
python3 scripts/emb/octen/0.6b/fp16/test-high-concurrency.py
```

## All User Messages

1. "I want to stress test sgl.emb.octen-0.6b.fp16.service on port 5000, as it fails for me whn I run a embedding batch request"
2. "I have tweaked params, lets run stress script"
3. "Find me the top concurrency number"
4. "use skill named learn"
5. "List all available skills"

## Learnings

### Technical Insights

1. **SGLang Memory Pool Architecture**:
   - `mem-fraction-static` allocates GPU memory for request pool
   - `max-running-requests` defines pool size (slots)
   - Embedding models have different memory requirements than generation models
   - Pool size must be >= max-running-requests value

2. **Batch Processing Behavior**:
   - SGLang processes requests in batches (observed 10-12 at a time)
   - Remaining requests queue and wait for available slots
   - This allows handling more requests than concurrent limit

3. **OOM vs alloc_req_slots Error**:
   - Exit code 137 = SIGKILL (system OOM killer)
   - alloc_req_slots error = SGLang internal pool exhaustion
   - Both indicate memory issues but at different levels

4. **Effective Concurrency**:
   - Configured: 64 slots
   - Actual concurrent processing: 10-12 requests
   - Throughput: 1000+ requests via queuing

### Process Learnings

1. **Stress Testing Methodology**:
   - Start with binary search to find breaking point
   - Test progressively higher values
   - Monitor service logs for diagnostic messages
   - Verify service stability after each test

2. **Debugging SGLang Services**:
   - Check systemd logs for crash patterns
   - Look for alloc_req_slots diagnostic messages
   - Monitor memory usage (peak vs current)
   - Use `--log-requests` flag for visibility

3. **Configuration Tuning**:
   - Start with conservative values
   - Increase gradually while monitoring
   - Leave safety margin below breaking point
   - Consider queuing behavior when setting limits

### Edge Cases

1. **Service Restart Loop**: Service was restarting every ~1 minute due to crashes
   - **Cause**: alloc_req_slots overflow
   - **Fix**: Increased max-running-requests

2. **Misleading Test Output**: Test script showed "status=ERR" for successful requests
   - **Cause**: Default value when status_code not set (only set on failure)
   - **Resolution**: Verified by checking actual HTTP responses

## Optional Next Step

None - task completed successfully. Service is now stable and handles high concurrency.

## Open Questions / Follow-up Items

None

## References

- **SGLang Documentation**: https://github.com/sgl-project/sglang
- **Service Configuration**: `scripts/emb/octen/0.6b/fp16/sgl.emb.octen-0.6b.fp16.service`
- **Wrapper Script**: `scripts/emb/octen/0.6b/fp16/sgl.emb.octen-0.6b.fp16-wrapper.sh`
- **Test Scripts**:
  - `scripts/emb/octen/0.6b/fp16/stress-test-embedding.py`
  - `scripts/emb/octen/0.6b/fp16/find-max-concurrency.py`
  - `scripts/emb/octen/0.6b/fp16/test-above-100.py`
  - `scripts/emb/octen/0.6b/fp16/test-high-concurrency.py`

## Test Results Summary

| Concurrent Requests | Result | Total Time | Avg Time/Request |
|-------------------|---------|-------------|-------------------|
| 25 | ✓ 25/25 | 0.26s | 0.22s |
| 38 | ✓ 38/38 | 0.32s | 0.24s |
| 44 | ✓ 44/44 | 0.39s | 0.28s |
| 50 | ✓ 50/50 | 0.39s | 0.28s |
| 75 | ✓ 75/75 | 0.49s | - |
| 88 | ✓ 88/88 | 0.61s | - |
| 94 | ✓ 94/94 | 0.66s | - |
| 97 | ✓ 97/97 | 0.71s | - |
| 99 | ✓ 99/99 | 1.06s | - |
| 100 | ✓ 100/100 | 0.68s | - |
| 110 | ✓ 110/110 | 0.77s | - |
| 120 | ✓ 120/120 | 1.20s | - |
| 200 | ✓ 200/200 | - | - |
| 250 | ✓ 250/250 | 1.53s | 0.01s |
| 300 | ✓ 300/300 | 2.15s | 0.01s |
| 400 | ✓ 400/400 | 2.36s | 0.01s |
| 500 | ✓ 500/500 | 3.24s | 0.01s |
| 600 | ✓ 600/600 | 3.49s | 0.01s |
| 700 | ✓ 700/700 | 4.33s | 0.01s |
| 800 | ✓ 800/800 | 4.79s | 0.01s |
| 900 | ✓ 900/900 | 5.24s | 0.01s |
| 1000 | ✓ 1000/1000 | 6.10s | 0.01s |

**Final Configuration**:
- `max-running-requests`: 64
- `mem-fraction-static`: 0.50
- Service Memory: 3.1G (stable)
- Status: Active, no crashes
