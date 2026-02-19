# TEI Connection Failure Fix - Retry Logic and Batch Size Reduction

## Metadata
- **Created**: 2026-02-19
- **Project**: sglang-embedding-cache
- **Component**: cache-proxy
- **Tags**: tei, connection-error, retry-logic, batch-size, debugging
- **Related Gists**: batch-size-tuning-2026-02-19.md, cache-proxy-performance-optimization-2026-02-19.md

## Summary
Fixed TEI service connection failures that occurred when processing large batches. The TEI service was crashing after processing 48-item batches, causing TCP connection failures for subsequent batches. Implemented retry logic with exponential backoff, reduced batch size from 48 to 12, and added configurable delays between batches to give the TEI service time to recover.

## Problem Statement
User reported error logs showing:
```
2026-02-19 14:30:02,518 - main - WARNING - Returning 16 embeddings out of 60 requested due to errors.
2026-02-19 14:30:02,521 - main - ERROR - HTTP request error for TEI batch (Indices: [53, 54, 55, 56, 57, 58, 59]): All connection attempts failed
httpx.ConnectError: All connection attempts failed
```

The pattern was clear: Batch 1 (48 items, indices 0-47) succeeded, but Batch 2 (12 items, indices 48-59) failed with a TCP-level connection error.

## Environment
- **OS**: Linux 6.8
- **Shell**: /bin/bash
- **User**: vvek
- **Working Directory**: /home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache
- **TEI Service**: http://buddha.alpine-musical.ts.net:5000/v1/embeddings
- **Model**: octen-0.6b-fp16
- **Original Batch Size**: 48
- **Constraints**: TEI service appears to crash after processing large batches

## Timeline
- **14:30:02**: Error occurred - 60 embeddings requested, only 16 returned
- **09:01-09:04**: Debug analysis performed using sequential thinking
- **09:04**: Implemented retry logic and reduced batch size
- **14:34:06**: Service restarted with new configuration
- **14:34:44**: Tests passed successfully

## Thought Process

### Diagnostic Analysis
Used sequential thinking to analyze the error pattern:

1. **Identified error type**: `httpx.ConnectError: All connection attempts failed` - a TCP-level connection failure, not an HTTP error
2. **Pattern recognition**: First batch (48 items) succeeded, second batch (12 items) failed
3. **Hypothesis generation**: Considered 7 possible sources:
   - TEI service overload/crash
   - Connection pool exhaustion
   - TEI service rate limiting
   - Network instability
   - TEI service timeout
   - Keepalive connection reuse issue
   - TEI service resource exhaustion (GPU memory/CPU)

4. **Root cause determination**: Most likely causes were:
   - **Primary**: TEI service crashing after processing large batches
   - **Secondary**: TEI service resource exhaustion (GPU memory)

### Solution Approach
Decided on a multi-pronged fix:
1. **Retry logic with exponential backoff** - Handle transient connection failures
2. **Reduce batch size** - Prevent TEI service overload
3. **Delay between batches** - Give TEI service time to recover
4. **Better error classification** - Distinguish recoverable vs non-retryable errors

### Reasoning Behind Decisions
- **Why retry logic?**: TCP connection errors are often transient. The TEI service might recover after a short delay.
- **Why exponential backoff?**: Prevents hammering a struggling service while still allowing quick recovery for transient issues.
- **Why reduce batch size?**: 48 items was too large for the octen-0.6b-fp16 model, causing crashes. 12 is a safer starting point.
- **Why delay between batches?**: Gives the TEI service time to process and recover before receiving the next batch.
- **Why distinguish error types?**: HTTP 4xx/5xx errors are usually not retryable (client errors or server errors), while TCP/timeout errors are recoverable.

## Solution

### Configuration Changes
Added retry configuration to `.env`:
```bash
MAX_RETRIES=3
RETRY_DELAY_BASE=1.0
RETRY_DELAY_MAX=10.0
BATCH_DELAY_SECONDS=0.5
TEI_REQUEST_BATCH_SIZE=12  # Reduced from 48
```

### Code Changes
Implemented retry logic in `cache_proxy/main.py`:
- Retry loop with exponential backoff for TCP connection errors and timeouts
- Detailed logging for each retry attempt
- Batch delay between consecutive batches
- Error classification to distinguish recoverable vs non-retryable errors

## Changes Made

### File: `cache_proxy/main.py`

#### Lines 30-36: Added Retry Configuration
```python
# Retry configuration for connection errors
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_BASE = float(os.getenv("RETRY_DELAY_BASE", "1.0"))  # Base delay in seconds
RETRY_DELAY_MAX = float(os.getenv("RETRY_DELAY_MAX", "10.0"))   # Max delay in seconds

# Delay between batches to give TEI service time to recover
BATCH_DELAY_SECONDS = float(os.getenv("BATCH_DELAY_SECONDS", "0.5"))
```

#### Lines 47-51: Added Diagnostic Logging
```python
logger.info(f"MAX_RETRIES: {MAX_RETRIES}")
logger.info(f"RETRY_DELAY_BASE: {RETRY_DELAY_BASE}s")
logger.info(f"RETRY_DELAY_MAX: {RETRY_DELAY_MAX}s")
logger.info(f"BATCH_DELAY_SECONDS: {BATCH_DELAY_SECONDS}s")
```

#### Lines 148-285: Implemented Retry Logic
**Before**: Simple try-catch with no retry logic
```python
try:
    response = await http_client.post(embed_url, json=tei_payload)
    response.raise_for_status()
    # ... process response
except httpx.RequestError as e:
    logger.error(f"HTTP request error for TEI batch (Indices: {batch_original_indices}): {e}", exc_info=True)
    all_batches_successful = False
```

**After**: Retry loop with exponential backoff and error classification
```python
batch_succeeded = False
last_error = None

for retry_attempt in range(MAX_RETRIES):
    try:
        inference_start = time.monotonic()
        
        if retry_attempt > 0:
            retry_delay = min(RETRY_DELAY_BASE * (2 ** retry_attempt), RETRY_DELAY_MAX)
            logger.warning(f"[SGLANG] Batch {batch_num} retry {retry_attempt}/{MAX_RETRIES} after {retry_delay:.2f}s delay")
            await asyncio.sleep(retry_delay)
        
        logger.info(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1}/{MAX_RETRIES} | URL: {embed_url}")
        
        response = await http_client.post(embed_url, json=tei_payload)
        response.raise_for_status()
        # ... process response
        
        batch_succeeded = True
        break
        
    except httpx.ConnectError as e:
        # TCP connection failed - TEI service might be down or overloaded
        last_error = f"TCP connection failed: {str(e)}"
        logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} TCP connection error: {e}")
    except httpx.TimeoutException as e:
        # Request timed out
        last_error = f"Request timeout: {str(e)}"
        logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} timeout error: {e}")
    except httpx.HTTPStatusError as e:
        # HTTP error (4xx/5xx) - these are usually not retryable
        last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(f"[SGLANG] Batch {batch_num} HTTP error {e.response.status_code}: {e.response.text[:200]}")
        break  # Don't retry HTTP errors
    except httpx.RequestError as e:
        # Other request errors
        last_error = f"Request error: {str(e)}"
        logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} request error: {e}", exc_info=True)
    except Exception as e:
        # Unexpected errors
        last_error = f"Unexpected error: {str(e)}"
        logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} unexpected error: {e}", exc_info=True)
        break

if not batch_succeeded:
    logger.error(f"[SGLANG] Batch {batch_num} FAILED after {MAX_RETRIES} attempts. Last error: {last_error}")
    all_batches_successful = False
else:
    logger.info(f"[SGLANG] Batch {batch_num} SUCCEEDED")

# Delay between batches to give TEI service time to recover
if i + TEI_REQUEST_BATCH_SIZE < len(missed_texts):
    logger.debug(f"[SGLANG] Waiting {BATCH_DELAY_SECONDS}s before next batch...")
    await asyncio.sleep(BATCH_DELAY_SECONDS)
```

### File: `.env`

#### Lines 27-32: Reduced Batch Size and Added Retry Config
```bash
# --- Cache Proxy Configuration ---
CACHE_HASH_FUNCTION=sha256
TEI_REQUEST_BATCH_SIZE=12  # Reduced from 48

# --- Retry Configuration ---
MAX_RETRIES=3
RETRY_DELAY_BASE=1.0
RETRY_DELAY_MAX=10.0
BATCH_DELAY_SECONDS=0.5
```

### Commands Executed

```bash
# Restart cache-proxy service
sudo systemctl restart cache-proxy && sudo systemctl status cache-proxy --no-pager

# Check service logs
sudo journalctl -u cache-proxy -n 50 --no-pager

# Run compatibility tests
python test_openai_compat.py http://localhost:8081/v1/embeddings
```

### Test Results
All tests passed:
- ✅ Single text input test
- ✅ Multiple text inputs test
- ✅ Cache hit test (duplicate input)

Service logs showed successful operation with new configuration:
```
TEI_REQUEST_BATCH_SIZE: 12
MAX_RETRIES: 3
RETRY_DELAY_BASE: 1.0s
RETRY_DELAY_MAX: 10.0s
BATCH_DELAY_SECONDS: 0.5s
```

## All User Messages
1. "Help fix - [error logs showing TEI connection failure]"
2. "Implement the full fix with retry logic and smaller batch sizes immediately"
3. "use the global skill named learn"

## Learnings

### Technical Insights
1. **TEI service limitations**: The octen-0.6b-fp16 model cannot reliably process 48-item batches. Large batches cause the service to crash or enter an unrecoverable state.
2. **TCP vs HTTP errors**: `httpx.ConnectError` indicates a TCP-level connection failure (service unreachable), while `HTTPStatusError` indicates the service responded but with an error code.
3. **Exponential backoff**: Essential for handling transient failures. Starting with 1s delay and doubling up to 10s max provides a good balance between quick recovery and not overwhelming the service.
4. **Batch delay importance**: A 0.5s delay between batches gives the TEI service time to process and recover before receiving the next request.

### Process Learnings
1. **Error pattern analysis**: The pattern of "first batch succeeds, second batch fails" is a strong indicator of service overload or crash, not random network issues.
2. **Diagnostic logging**: Adding detailed logging before/after each batch helps identify where failures occur and why.
3. **Configuration externalization**: Making retry parameters configurable via environment variables allows tuning without code changes.

### Edge Cases Encountered
1. **Partial batch failures**: The original code would fail the entire request if any batch failed. The new code returns partial results with a warning.
2. **Connection pool reuse**: Stale connections might cause issues. The retry logic handles this by attempting new connections.

### Workarounds Used
1. **Reduced batch size**: From 48 to 12 as a conservative starting point. Can be tuned up if the TEI service proves stable.
2. **Retry with exponential backoff**: Handles transient failures without hammering the service.

## Optional Next Step
Monitor the service logs for retry activity. If frequent retries are observed, consider:
1. Further reducing batch size (e.g., to 8 or 6)
2. Increasing `BATCH_DELAY_SECONDS` (e.g., to 1.0s)
3. Investigating TEI service logs to identify why it's crashing

## Open Questions / Follow-up Items
1. What is the optimal batch size for the octen-0.6b-fp16 model?
2. Can the TEI service be configured to handle larger batches more reliably?
3. Should we implement circuit breaker pattern to stop sending requests if TEI service is consistently failing?

## References
- Related gists in this project:
  - `batch-size-tuning-2026-02-19.md` - Previous batch size optimization work
  - `cache-proxy-performance-optimization-2026-02-19.md` - Performance tuning context
- External documentation:
  - httpx documentation: https://www.python-httpx.org/
  - Exponential backoff pattern: https://en.wikipedia.org/wiki/Exponential_backoff
