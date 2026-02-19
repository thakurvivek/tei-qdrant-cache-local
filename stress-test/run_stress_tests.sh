#!/bin/bash
# Stress Test Runner for Embedding Cache Proxy
# Runs multiple test scenarios with different configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
URL="${EMBEDDING_CACHE_URL:-http://localhost:8081/v1/embeddings}"
OUTPUT_DIR="${OUTPUT_DIR:-./stress_test_results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Embedding Cache Stress Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Target URL: ${GREEN}$URL${NC}"
echo -e "Output Directory: ${GREEN}$OUTPUT_DIR${NC}"
echo -e "Timestamp: ${GREEN}$TIMESTAMP${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to run a single test scenario
run_test() {
    local test_name=$1
    local requests=$2
    local concurrency=$3
    local duration=$4
    local cache_hit_ratio=$5
    local warmup=$6

    echo -e "${YELLOW}Running: $test_name${NC}"
    echo -e "  Requests: $requests, Concurrency: $concurrency"
    echo -e "  Duration: ${duration:-N/A}, Cache Hit Ratio: $cache_hit_ratio"
    echo -e "  Warmup: $warmup"
    echo ""

    local output_file="$OUTPUT_DIR/${test_name}_${TIMESTAMP}.json"

    python3 stress_test.py \
        "$URL" \
        --requests "$requests" \
        --concurrency "$concurrency" \
        ${duration:+--duration "$duration"} \
        --cache-hit-ratio "$cache_hit_ratio" \
        --warmup "$warmup" \
        --output "$output_file" \
        --sample-count 200

    echo -e "${GREEN}✓ Completed: $test_name${NC}"
    echo ""
}

# Check if the service is available
echo -e "${YELLOW}Checking if service is available...${NC}"
if curl -s -f "$URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Service is available${NC}"
else
    echo -e "${RED}✗ Service is not available at $URL${NC}"
    echo -e "${YELLOW}Please ensure the cache proxy is running${NC}"
    exit 1
fi
echo ""

# ============================================
# Test Scenarios
# ============================================

# Scenario 1: Baseline Test - Low concurrency, moderate requests
run_test \
    "01_baseline" \
    100 \
    10 \
    "" \
    0.3 \
    20

# Scenario 2: High Concurrency Test - Many concurrent requests
run_test \
    "02_high_concurrency" \
    500 \
    100 \
    "" \
    0.3 \
    50

# Scenario 3: Cache Hit Test - High cache hit ratio
run_test \
    "03_cache_hit" \
    500 \
    50 \
    "" \
    0.8 \
    100

# Scenario 4: Cache Miss Test - Low cache hit ratio
run_test \
    "04_cache_miss" \
    500 \
    50 \
    "" \
    0.1 \
    20

# Scenario 5: Sustained Load Test - Duration-based
run_test \
    "05_sustained_load" \
    0 \
    50 \
    60 \
    0.5 \
    100

# Scenario 6: Burst Test - Very high concurrency
run_test \
    "06_burst" \
    200 \
    200 \
    "" \
    0.3 \
    50

# Scenario 7: Large Payload Test - More sample texts
run_test \
    "07_large_payload" \
    300 \
    30 \
    "" \
    0.4 \
    50

# ============================================
# Summary
# ============================================

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Stress Test Suite Completed${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Results saved to: ${GREEN}$OUTPUT_DIR${NC}"
echo ""
echo -e "${YELLOW}To analyze results, you can:${NC}"
echo -e "  1. Review individual JSON files"
echo -e "  2. Run: python3 analyze_stress_results.py $OUTPUT_DIR"
echo -e "${BLUE}========================================${NC}"
