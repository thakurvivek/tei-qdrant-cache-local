#!/usr/bin/env python3
"""
Comprehensive Stress Test for Embedding Cache Proxy

This script performs stress testing with:
- Cache hit/miss tracking
- Realistic test data generation
- System resource monitoring
- Multiple test scenarios
- Detailed metrics and reporting
"""

import asyncio
import httpx
import time
import random
import argparse
import statistics
import json
import logging
import psutil
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class TestMetrics:
    """Container for test metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_duration: float = 0.0
    latencies: List[float] = None
    cache_hit_latencies: List[float] = None
    cache_miss_latencies: List[float] = None
    status_codes: Dict[int, int] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []
        if self.cache_hit_latencies is None:
            self.cache_hit_latencies = []
        if self.cache_miss_latencies is None:
            self.cache_miss_latencies = []
        if self.status_codes is None:
            self.status_codes = {}
        if self.errors is None:
            self.errors = []


@dataclass
class SystemMetrics:
    """Container for system resource metrics"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0


class StressTester:
    """Main stress testing class"""

    def __init__(self, url: str, sample_texts: List[str]):
        self.url = url
        self.sample_texts = sample_texts
        self.metrics = TestMetrics()
        self.system_metrics_start = SystemMetrics()
        self.system_metrics_end = SystemMetrics()
        self.process = psutil.Process(os.getpid())

    def capture_system_metrics(self) -> SystemMetrics:
        """Capture current system resource metrics"""
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        net_io = psutil.net_io_counters()

        return SystemMetrics(
            cpu_percent=cpu,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            disk_io_read_mb=disk_io.read_bytes / (1024 * 1024) if disk_io else 0.0,
            disk_io_write_mb=disk_io.write_bytes / (1024 * 1024) if disk_io else 0.0,
            network_sent_mb=net_io.bytes_sent / (1024 * 1024) if net_io else 0.0,
            network_recv_mb=net_io.bytes_recv / (1024 * 1024) if net_io else 0.0,
        )

    async def send_request(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        request_data: Dict[str, Any],
        request_id: int,
    ) -> Tuple[Optional[float], Optional[int], bool, Optional[bool]]:
        """
        Sends a single request, measures latency, and handles errors.
        Returns: (latency, status_code, success, is_cache_hit)
        """
        latency: Optional[float] = None
        status_code: Optional[int] = None
        success = False
        is_cache_hit: Optional[bool] = None

        async with semaphore:
            start_time = time.monotonic()
            try:
                response = await client.post(
                    self.url,
                    json=request_data,
                    timeout=60.0,
                    headers={"X-Request-ID": str(request_id)}
                )
                latency = time.monotonic() - start_time
                status_code = response.status_code

                if 200 <= status_code < 300:
                    success = True
                    # Try to detect cache hit from response headers or timing
                    # Fast responses (< 10ms) are likely cache hits
                    is_cache_hit = latency < 0.01
                    logger.debug(f"Request {request_id} successful ({status_code}) - "
                               f"Latency: {latency:.4f}s - Cache: {'HIT' if is_cache_hit else 'MISS'}")
                else:
                    logger.warning(
                        f"Request {request_id} failed with status {status_code} - "
                        f"Latency: {latency:.4f}s - Response: {response.text[:200]}"
                    )

            except httpx.TimeoutException:
                latency = time.monotonic() - start_time
                logger.warning(f"Request {request_id} timed out after {latency:.4f}s")
            except httpx.RequestError as e:
                latency = time.monotonic() - start_time
                logger.error(f"Request {request_id} failed: {e.__class__.__name__} - {e}")
            except Exception as e:
                latency = time.monotonic() - start_time
                logger.error(f"Request {request_id} unexpected error: {e}", exc_info=True)

            return latency, status_code, success, is_cache_hit

    async def run_load_test(
        self,
        total_requests: int,
        concurrency: int,
        duration: Optional[float] = None,
        warmup_requests: int = 0,
        cache_hit_ratio: float = 0.3,
    ) -> TestMetrics:
        """
        Runs the load test with specified parameters.

        Args:
            total_requests: Total number of requests to send
            concurrency: Number of concurrent requests
            duration: Optional duration in seconds (overrides total_requests)
            warmup_requests: Number of warmup requests before actual test
            cache_hit_ratio: Target cache hit ratio (0.0 to 1.0)
        """
        self.metrics = TestMetrics()
        semaphore = asyncio.Semaphore(concurrency)
        tasks = []

        logger.info(
            f"Starting stress test: URL={self.url}, "
            f"Concurrency={concurrency}, "
            f"Target Cache Hit Ratio={cache_hit_ratio:.1%}"
        )

        # Capture initial system metrics
        self.system_metrics_start = self.capture_system_metrics()

        # Warmup phase
        if warmup_requests > 0:
            logger.info(f"Running warmup phase with {warmup_requests} requests...")
            await self._run_warmup(warmup_requests, concurrency)

        # Main test phase
        overall_start_time = time.monotonic()
        request_id = 0

        async with httpx.AsyncClient() as client:
            if duration:
                # Duration-based test
                logger.info(f"Running duration-based test for {duration}s...")
                end_time = overall_start_time + duration

                while time.monotonic() < end_time:
                    # Prepare request data
                    text_input = self._select_text(cache_hit_ratio)
                    payload = {"input": text_input}

                    task = asyncio.create_task(
                        self.send_request(client, semaphore, payload, request_id)
                    )
                    tasks.append(task)
                    request_id += 1

                    # Small delay to prevent overwhelming
                    await asyncio.sleep(0.001)

            else:
                # Request count-based test
                logger.info(f"Running request-based test with {total_requests} requests...")
                for i in range(total_requests):
                    text_input = self._select_text(cache_hit_ratio)
                    payload = {"input": text_input}

                    task = asyncio.create_task(
                        self.send_request(client, semaphore, payload, request_id)
                    )
                    tasks.append(task)
                    request_id += 1

            # Wait for all tasks to complete
            logger.info(f"Waiting for {len(tasks)} requests to complete...")
            raw_results = await asyncio.gather(*tasks)

        overall_end_time = time.monotonic()
        self.metrics.total_duration = overall_end_time - overall_start_time

        # Capture final system metrics
        self.system_metrics_end = self.capture_system_metrics()

        # Process results
        self._process_results(raw_results)

        return self.metrics

    async def _run_warmup(self, warmup_requests: int, concurrency: int):
        """Run warmup requests to populate cache"""
        semaphore = asyncio.Semaphore(concurrency)
        tasks = []

        async with httpx.AsyncClient() as client:
            for i in range(warmup_requests):
                # Use unique texts for warmup to populate cache
                text_input = f"Warmup text {i}: {self.sample_texts[i % len(self.sample_texts)]}"
                payload = {"input": text_input}

                task = asyncio.create_task(
                    self.send_request(client, semaphore, payload, i)
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

        logger.info(f"Warmup completed with {warmup_requests} requests")

    def _select_text(self, cache_hit_ratio: float) -> str:
        """Select text based on desired cache hit ratio"""
        if random.random() < cache_hit_ratio:
            # Return a text likely to be in cache (from first 20% of samples)
            return random.choice(self.sample_texts[:max(1, len(self.sample_texts) // 5)])
        else:
            # Return a text likely to be a cache miss (from remaining samples)
            return random.choice(self.sample_texts[max(1, len(self.sample_texts) // 5):])

    def _process_results(self, raw_results: List[Tuple]):
        """Process raw results and populate metrics"""
        for latency, status, success, is_cache_hit in raw_results:
            self.metrics.total_requests += 1

            if success and latency is not None:
                self.metrics.successful_requests += 1
                self.metrics.latencies.append(latency)

                if is_cache_hit is not None:
                    if is_cache_hit:
                        self.metrics.cache_hits += 1
                        self.metrics.cache_hit_latencies.append(latency)
                    else:
                        self.metrics.cache_misses += 1
                        self.metrics.cache_miss_latencies.append(latency)
            else:
                self.metrics.failed_requests += 1
                if status is not None:
                    self.metrics.status_codes[status] = self.metrics.status_codes.get(status, 0) + 1
                else:
                    self.metrics.status_codes[0] = self.metrics.status_codes.get(0, 0) + 1

    def calculate_percentiles(self, latencies: List[float], percentiles: List[int]) -> Dict[int, float]:
        """Calculate specified percentiles from a list of latencies"""
        if not latencies:
            return {p: 0.0 for p in percentiles}

        latencies_sorted = sorted(latencies)
        results = {}
        for p in percentiles:
            if p < 0 or p > 100:
                continue
            index = int(len(latencies_sorted) * p / 100)
            index = min(index, len(latencies_sorted) - 1)
            results[p] = latencies_sorted[index]
        return results

    def print_report(self):
        """Print comprehensive test report"""
        metrics = self.metrics
        rps = metrics.successful_requests / metrics.total_duration if metrics.total_duration > 0 else 0
        cache_hit_rate = (metrics.cache_hits / metrics.successful_requests * 100) if metrics.successful_requests > 0 else 0

        print("\n" + "=" * 60)
        print("STRESS TEST REPORT")
        print("=" * 60)
        print(f"Target URL:          {self.url}")
        print(f"Total Duration:      {metrics.total_duration:.2f} s")
        print("-" * 60)
        print("REQUEST METRICS:")
        print(f"  Total Requests:     {metrics.total_requests}")
        print(f"  Successful:         {metrics.successful_requests}")
        print(f"  Failed:             {metrics.failed_requests}")
        print(f"  Success Rate:       {(metrics.successful_requests / metrics.total_requests * 100):.2f}%")
        print(f"  Requests/Second:    {rps:.2f} RPS")
        print("-" * 60)
        print("CACHE METRICS:")
        print(f"  Cache Hits:         {metrics.cache_hits}")
        print(f"  Cache Misses:       {metrics.cache_misses}")
        print(f"  Cache Hit Rate:     {cache_hit_rate:.2f}%")
        print("-" * 60)
        print("LATENCY METRICS (All Requests):")
        if metrics.latencies:
            print(f"  Average:            {statistics.mean(metrics.latencies):.4f} s")
            print(f"  Median:             {statistics.median(metrics.latencies):.4f} s")
            print(f"  Min:                {min(metrics.latencies):.4f} s")
            print(f"  Max:                {max(metrics.latencies):.4f} s")
            percentiles = self.calculate_percentiles(metrics.latencies, [50, 90, 95, 99])
            print(f"  50th Percentile:    {percentiles.get(50, 0.0):.4f} s")
            print(f"  90th Percentile:    {percentiles.get(90, 0.0):.4f} s")
            print(f"  95th Percentile:    {percentiles.get(95, 0.0):.4f} s")
            print(f"  99th Percentile:    {percentiles.get(99, 0.0):.4f} s")
        print("-" * 60)
        print("LATENCY METRICS (Cache Hits Only):")
        if metrics.cache_hit_latencies:
            print(f"  Average:            {statistics.mean(metrics.cache_hit_latencies):.4f} s")
            print(f"  Median:             {statistics.median(metrics.cache_hit_latencies):.4f} s")
            print(f"  Min:                {min(metrics.cache_hit_latencies):.4f} s")
            print(f"  Max:                {max(metrics.cache_hit_latencies):.4f} s")
        print("-" * 60)
        print("LATENCY METRICS (Cache Misses Only):")
        if metrics.cache_miss_latencies:
            print(f"  Average:            {statistics.mean(metrics.cache_miss_latencies):.4f} s")
            print(f"  Median:             {statistics.median(metrics.cache_miss_latencies):.4f} s")
            print(f"  Min:                {min(metrics.cache_miss_latencies):.4f} s")
            print(f"  Max:                {max(metrics.cache_miss_latencies):.4f} s")
        print("-" * 60)
        print("SYSTEM RESOURCE METRICS:")
        print(f"  CPU Usage:           {self.system_metrics_start.cpu_percent:.1f}% -> "
              f"{self.system_metrics_end.cpu_percent:.1f}%")
        print(f"  Memory Usage:        {self.system_metrics_start.memory_percent:.1f}% -> "
              f"{self.system_metrics_end.memory_percent:.1f}% "
              f"({self.system_metrics_start.memory_used_mb:.1f}MB -> "
              f"{self.system_metrics_end.memory_used_mb:.1f}MB)")
        print(f"  Disk Read:           {self.system_metrics_end.disk_io_read_mb - self.system_metrics_start.disk_io_read_mb:.2f} MB")
        print(f"  Disk Write:          {self.system_metrics_end.disk_io_write_mb - self.system_metrics_start.disk_io_write_mb:.2f} MB")
        print(f"  Network Sent:        {self.system_metrics_end.network_sent_mb - self.system_metrics_start.network_sent_mb:.2f} MB")
        print(f"  Network Received:    {self.system_metrics_end.network_recv_mb - self.system_metrics_start.network_recv_mb:.2f} MB")
        print("-" * 60)
        print("STATUS CODE DISTRIBUTION:")
        for code in sorted(metrics.status_codes.keys()):
            count = metrics.status_codes[code]
            status_label = f"{code}" if code > 0 else "Errors (No Status)"
            print(f"  {status_label}:             {count}")
        print("=" * 60 + "\n")

    def save_results(self, filename: Optional[str] = None):
        """Save test results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stress_test_results_{timestamp}.json"

        results = {
            "timestamp": datetime.now().isoformat(),
            "url": self.url,
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "successful_requests": self.metrics.successful_requests,
                "failed_requests": self.metrics.failed_requests,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "total_duration": self.metrics.total_duration,
                "latencies": self.metrics.latencies,
                "cache_hit_latencies": self.metrics.cache_hit_latencies,
                "cache_miss_latencies": self.metrics.cache_miss_latencies,
                "status_codes": self.metrics.status_codes,
            },
            "system_metrics": {
                "start": asdict(self.system_metrics_start),
                "end": asdict(self.system_metrics_end),
            },
            "statistics": {
                "rps": self.metrics.successful_requests / self.metrics.total_duration if self.metrics.total_duration > 0 else 0,
                "cache_hit_rate": (self.metrics.cache_hits / self.metrics.successful_requests * 100) if self.metrics.successful_requests > 0 else 0,
                "avg_latency": statistics.mean(self.metrics.latencies) if self.metrics.latencies else 0.0,
                "median_latency": statistics.median(self.metrics.latencies) if self.metrics.latencies else 0.0,
                "p50_latency": self.calculate_percentiles(self.metrics.latencies, [50]).get(50, 0.0) if self.metrics.latencies else 0.0,
                "p90_latency": self.calculate_percentiles(self.metrics.latencies, [90]).get(90, 0.0) if self.metrics.latencies else 0.0,
                "p95_latency": self.calculate_percentiles(self.metrics.latencies, [95]).get(95, 0.0) if self.metrics.latencies else 0.0,
                "p99_latency": self.calculate_percentiles(self.metrics.latencies, [99]).get(99, 0.0) if self.metrics.latencies else 0.0,
            }
        }

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Results saved to {filename}")


def generate_sample_texts(count: int = 100) -> List[str]:
    """Generate sample texts for testing"""
    base_texts = [
        "This is a test sentence for embedding.",
        "Deep learning has revolutionized many fields of computer science.",
        "Natural language processing enables computers to understand human text.",
        "The quick brown fox jumps over the lazy dog.",
        "Artificial intelligence is transforming industries worldwide.",
        "Machine learning models require large amounts of training data.",
        "Vector embeddings represent text as numerical vectors in high-dimensional space.",
        "Cache optimization can significantly improve application performance.",
        "Distributed systems require careful coordination and consistency management.",
        "Real-time applications demand low latency responses.",
    ]

    # Generate variations
    texts = []
    for i in range(count):
        base = base_texts[i % len(base_texts)]
        # Add some variations
        if i % 3 == 0:
            texts.append(base)
        elif i % 3 == 1:
            texts.append(base + f" Variation {i}.")
        else:
            texts.append(f"{i}. {base}")

    return texts


async def main():
    parser = argparse.ArgumentParser(
        description="Stress test the embedding cache proxy with comprehensive metrics"
    )
    parser.add_argument(
        "url",
        help="Target URL for the embeddings endpoint (e.g., http://localhost:8081/v1/embeddings)",
    )
    parser.add_argument(
        "-r",
        "--requests",
        type=int,
        default=1000,
        help="Total number of requests to send (default: 1000)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=50,
        help="Number of concurrent requests (default: 50)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help="Duration in seconds (overrides --requests)",
    )
    parser.add_argument(
        "-w",
        "--warmup",
        type=int,
        default=100,
        help="Number of warmup requests (default: 100)",
    )
    parser.add_argument(
        "--cache-hit-ratio",
        type=float,
        default=0.3,
        help="Target cache hit ratio 0.0-1.0 (default: 0.3)",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=100,
        help="Number of sample texts to generate (default: 100)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output JSON file for results",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)

    # Generate sample texts
    sample_texts = generate_sample_texts(args.sample_count)
    logger.info(f"Generated {len(sample_texts)} sample texts")

    # Create tester and run test
    tester = StressTester(args.url, sample_texts)
    await tester.run_load_test(
        total_requests=args.requests,
        concurrency=args.concurrency,
        duration=args.duration,
        warmup_requests=args.warmup,
        cache_hit_ratio=args.cache_hit_ratio,
    )

    # Print and save results
    tester.print_report()
    tester.save_results(args.output)


if __name__ == "__main__":
    asyncio.run(main())
