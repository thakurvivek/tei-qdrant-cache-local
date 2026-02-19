# Embedding Cache Stress Testing Guide

This guide explains how to stress test the embedding cache proxy to evaluate its performance under various load conditions.

## Overview

The stress testing suite consists of three main components:

1. **[`stress_test.py`](stress_test.py)** - Core stress testing script with comprehensive metrics
2. **[`run_stress_tests.sh`](run_stress_tests.sh)** - Automated test runner with multiple scenarios
3. **[`analyze_stress_results.py`](analyze_stress_results.py)** - Results analysis and comparison tool

## Prerequisites

### Required Python Packages

```bash
pip install httpx psutil
```

Or install from requirements:

```bash
pip install -r cache_proxy/requirements.txt
```

### System Requirements

- Python 3.8+
- Running cache proxy service
- Sufficient system resources for concurrent testing

## Quick Start

### 1. Start the Cache Proxy

Ensure your cache proxy is running:

```bash
# Using systemd
sudo systemctl start cache-proxy

# Or manually
cd cache_proxy && python3 main.py
```

### 2. Run a Quick Test

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -r 100 -c 10
```

### 3. Run Full Test Suite

```bash
chmod +x run_stress_tests.sh
./run_stress_tests.sh
```

## Using [`stress_test.py`](stress_test.py)

### Basic Usage

```bash
python3 stress_test.py <URL> [OPTIONS]
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | Target URL for embeddings endpoint (required) | - |
| `-r, --requests` | Total number of requests to send | 1000 |
| `-c, --concurrency` | Number of concurrent requests | 50 |
| `-d, --duration` | Duration in seconds (overrides `--requests`) | None |
| `-w, --warmup` | Number of warmup requests | 100 |
| `--cache-hit-ratio` | Target cache hit ratio (0.0-1.0) | 0.3 |
| `--sample-count` | Number of sample texts to generate | 100 |
| `-o, --output` | Output JSON file for results | auto-generated |
| `-v, --verbose` | Enable debug logging | False |

### Examples

#### Basic Load Test

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -r 500 -c 20
```

#### Duration-Based Test

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -d 60 -c 50
```

#### High Cache Hit Test

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -r 1000 -c 50 --cache-hit-ratio 0.8
```

#### Burst Test

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -r 200 -c 200 -w 50
```

#### With Custom Output

```bash
python3 stress_test.py http://localhost:8081/v1/embeddings -r 500 -c 30 -o my_test_results.json
```

## Using [`run_stress_tests.sh`](run_stress_tests.sh)

The test runner executes multiple predefined test scenarios to evaluate different aspects of the cache performance.

### Test Scenarios

| Scenario | Description | Requests | Concurrency | Duration | Cache Hit Ratio |
|----------|-------------|----------|-------------|----------|-----------------|
| `01_baseline` | Baseline performance test | 100 | 10 | - | 30% |
| `02_high_concurrency` | High concurrency stress | 500 | 100 | - | 30% |
| `03_cache_hit` | High cache hit rate | 500 | 50 | - | 80% |
| `04_cache_miss` | Low cache hit rate | 500 | 50 | - | 10% |
| `05_sustained_load` | Sustained load over time | - | 50 | 60s | 50% |
| `06_burst` | Burst traffic test | 200 | 200 | - | 30% |
| `07_large_payload` | Large payload handling | 300 | 30 | - | 40% |

### Running the Test Suite

```bash
# Make executable
chmod +x run_stress_tests.sh

# Run with default URL
./run_stress_tests.sh

# Run with custom URL
EMBEDDING_CACHE_URL=http://your-server:8081/v1/embeddings ./run_stress_tests.sh

# Run with custom output directory
OUTPUT_DIR=./my_results ./run_stress_tests.sh
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `EMBEDDING_CACHE_URL` | Target URL for tests | `http://localhost:8081/v1/embeddings` |
| `OUTPUT_DIR` | Directory for result files | `./stress_test_results` |

## Using [`analyze_stress_results.py`](analyze_stress_results.py)

Analyze and compare results from multiple test runs.

### Basic Usage

```bash
python3 analyze_stress_results.py <results_directory>
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `results_dir` | Directory containing result JSON files (required) | - |
| `-o, --output` | Output markdown report file | None |
| `--pattern` | File pattern to match | `*.json` |

### Examples

#### Analyze All Results

```bash
python3 analyze_stress_results.py ./stress_test_results
```

#### Generate Markdown Report

```bash
python3 analyze_stress_results.py ./stress_test_results -o report.md
```

#### Analyze Specific Tests

```bash
python3 analyze_stress_results.py ./stress_test_results --pattern "baseline*.json"
```

## Understanding the Metrics

### Request Metrics

- **Total Requests**: Number of requests sent
- **Successful Requests**: Requests that completed successfully (2xx status)
- **Failed Requests**: Requests that failed or timed out
- **Success Rate**: Percentage of successful requests
- **Requests/Second (RPS)**: Throughput metric

### Cache Metrics

- **Cache Hits**: Requests served from cache (detected by latency < 10ms)
- **Cache Misses**: Requests that required embedding generation
- **Cache Hit Rate**: Percentage of requests served from cache

### Latency Metrics

- **Average**: Mean latency across all successful requests
- **Median**: 50th percentile latency
- **P50/P90/P95/P99**: Percentile latencies (tail latency analysis)
- **Min/Max**: Minimum and maximum observed latencies

### System Resource Metrics

- **CPU Usage**: CPU utilization percentage (start/end)
- **Memory Usage**: Memory utilization and used MB (start/end)
- **Disk I/O**: Read/write operations in MB
- **Network I/O**: Sent/received data in MB

## Interpreting Results

### Cache Performance

A well-performing cache should show:

- **High cache hit rate** (>70%): Most requests served from cache
- **Low cache hit latency** (<10ms): Fast cache responses
- **Significant latency difference**: Cache hits should be much faster than misses

### Throughput

- **RPS**: Higher is better, but depends on hardware
- **Success rate**: Should be >99% under normal load
- **Latency vs RPS**: Monitor how latency increases with throughput

### System Resources

- **CPU**: Should not consistently exceed 80%
- **Memory**: Should have headroom for growth
- **Disk/Network**: Should not be bottlenecks

### Red Flags

- **High failure rate** (>1%): Indicates stability issues
- **Increasing P99 latency**: Suggests resource contention
- **Memory growth**: Possible memory leak
- **CPU saturation**: System at capacity

## Advanced Usage

### Custom Test Scenarios

Create your own test scenarios by modifying [`run_stress_tests.sh`](run_stress_tests.sh):

```bash
run_test \
    "my_custom_test" \
    1000 \
    100 \
    "" \
    0.5 \
    100
```

### Integration with CI/CD

Add stress tests to your CI pipeline:

```yaml
# Example GitHub Actions
- name: Run Stress Tests
  run: |
    python3 stress_test.py http://localhost:8081/v1/embeddings -r 100 -c 10
    python3 analyze_stress_results.py ./stress_test_results -o report.md
```

### Monitoring During Tests

Use system monitoring tools alongside stress tests:

```bash
# In one terminal
./run_stress_tests.sh

# In another terminal
htop
# or
watch -n 1 'ps aux | grep python'
```

## Troubleshooting

### Service Not Available

```
✗ Service is not available at http://localhost:8081/v1/embeddings
```

**Solution**: Ensure the cache proxy is running and accessible.

### Connection Refused

```
Request failed: ConnectError
```

**Solution**: Check firewall settings and service port configuration.

### High Failure Rate

**Possible causes**:
- Service overloaded (reduce concurrency)
- Timeout too short (increase timeout in [`stress_test.py`](stress_test.py))
- Resource exhaustion (check system resources)

### Inconsistent Results

**Possible causes**:
- Background processes consuming resources
- Network variability
- Cache state not reset between tests

## Best Practices

1. **Warm up the cache**: Use warmup requests to populate cache before testing
2. **Test incrementally**: Start with low concurrency, increase gradually
3. **Monitor resources**: Watch CPU, memory, and disk during tests
4. **Repeat tests**: Run multiple iterations to identify variability
5. **Document conditions**: Record system state and configuration
6. **Compare baselines**: Track performance over time
7. **Test realistic scenarios**: Match production traffic patterns

## File Structure

```
.
├── stress_test.py              # Core stress testing script
├── run_stress_tests.sh         # Test runner with scenarios
├── analyze_stress_results.py   # Results analysis tool
├── stress_test_results/        # Default output directory
│   ├── 01_baseline_*.json
│   ├── 02_high_concurrency_*.json
│   └── ...
└── STRESS_TEST_README.md       # This file
```

## Contributing

To add new test scenarios:

1. Edit [`run_stress_tests.sh`](run_stress_tests.sh)
2. Add a new `run_test` call with appropriate parameters
3. Document the scenario in this README

## License

Same as the main project.
