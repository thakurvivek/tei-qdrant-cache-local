#!/bin/bash
# Monitor embedding workload - GPU, Cache Proxy, and SGLang

echo "=== Starting Workload Monitoring ==="
echo "Press Ctrl+C to stop"
echo ""

# Get current timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/monitoring"
mkdir -p "$LOG_DIR"

# Start GPU monitoring in background
echo "Starting GPU monitoring..."
gpustat -i 1 > "$LOG_DIR/gpu_$TIMESTAMP.log" 2>&1 &
GPU_PID=$!
echo "GPU monitoring PID: $GPU_PID"

# Start cache proxy log monitoring
echo "Starting cache proxy log monitoring..."
journalctl -u cache-proxy -f > "$LOG_DIR/cache_proxy_$TIMESTAMP.log" 2>&1 &
CACHE_PID=$!
echo "Cache proxy monitoring PID: $CACHE_PID"

# Start SGLang log monitoring (if running as service)
if systemctl is-active --quiet sglang 2>/dev/null; then
    echo "Starting SGLang log monitoring..."
    journalctl -u sglang -f > "$LOG_DIR/sglang_$TIMESTAMP.log" 2>&1 &
    SGLANG_PID=$!
    echo "SGLang monitoring PID: $SGLANG_PID"
else
    echo "SGLang service not found or not active"
    SGLANG_PID=""
fi

echo ""
echo "=== Monitoring Active ==="
echo "GPU logs: $LOG_DIR/gpu_$TIMESTAMP.log"
echo "Cache logs: $LOG_DIR/cache_proxy_$TIMESTAMP.log"
if [ -n "$SGLANG_PID" ]; then
    echo "SGLang logs: $LOG_DIR/sglang_$TIMESTAMP.log"
fi
echo ""
echo "PIDs to kill: $GPU_PID $CACHE_PID $SGLANG_PID"
echo ""
echo "=== Real-time Stats ==="

# Show real-time stats loop
trap "echo ''; echo 'Stopping monitoring...'; kill $GPU_PID $CACHE_PID $SGLANG_PID 2>/dev/null; echo 'Monitoring stopped. Logs saved to $LOG_DIR'; exit 0" INT TERM

while true; do
    clear
    echo "=== Workload Monitoring - $(date) ==="
    echo ""
    
    # GPU stats
    echo "--- GPU Status ---"
    nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv,noheader,nounits
    echo ""
    
    # Cache proxy stats from logs
    echo "--- Recent Cache Activity ---"
    journalctl -u cache-proxy -n 5 --no-pager | grep -E "Hit Rate|SUMMARY|Upserting" || echo "No recent activity"
    echo ""
    
    # Qdrant collection stats
    echo "--- Qdrant Collection ---"
    curl -s http://buddha.alpine-musical.ts.net:6335/collections/text_embedding_cache_octen-0.6b-fp16 | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"Points: {data.get('result', {}).get('points_count', 'N/A')}\")" 2>/dev/null || echo "Unable to fetch"
    echo ""
    
    # System load
    echo "--- System Load ---"
    uptime
    echo ""
    
    sleep 2
done
