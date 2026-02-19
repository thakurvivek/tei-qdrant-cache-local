#!/usr/bin/env python3
"""
Batch Size Tuning Script for Cache Proxy

Tests different TEI_REQUEST_BATCH_SIZE values to find optimal throughput.
Measures latency, throughput, and cache hit rate for each batch size.
"""

import asyncio
import httpx
import time
import os
import argparse
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import subprocess
import json


@dataclass
class BatchSizeResult:
    """Results for a single batch size test"""
    batch_size: int
    total_requests: int
    successful_requests: int
    avg_latency: float
    p50_latency: float
    p95_latency: float
    p99_latency: float
    requests_per_second: float
    cache_hit_rate: float


class BatchSizeTuner:
    """Tunes TEI_REQUEST_BATCH_SIZE by testing different values"""

    def __init__(self, proxy_url: str, sample_texts: List[str]):
        self.proxy_url = proxy_url
        self.sample_texts = sample_texts

    async def test_batch_size(
        self,
        batch_size: int,
        num_requests: int = 100,
        concurrency: int = 20
    ) -> BatchSizeResult:
        """Test a specific batch size configuration"""
        print(f"\n{'='*60}")
        print(f"Testing batch_size={batch_size}")
        print(f"{'='*60}")

        # Update .env with new batch size
        self._update_env_batch_size(batch_size)

        # Restart cache proxy service
        print(f"Restarting cache proxy service...")
        self._restart_cache_proxy()
        await asyncio.sleep(5)  # Wait for service to start

        # Run performance test
        latencies = []
        cache_hits = 0
        cache_misses = 0
        successful = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            semaphore = asyncio.Semaphore(concurrency)

            async def send_request(text: str, req_id: int):
                async with semaphore:
                    start = time.monotonic()
                    try:
                        response = await client.post(
                            self.proxy_url,
                            json={"input": text},
                            headers={"X-Request-ID": str(req_id)}
                        )
                        latency = time.monotonic() - start

                        if response.status_code == 200:
                            # Try to detect cache hit from timing
                            # Fast responses (< 10ms) are likely cache hits
                            is_cache_hit = latency < 0.01
                            return latency, True, is_cache_hit
                        else:
                            return latency, False, None
                    except Exception as e:
                        print(f"Request {req_id} failed: {e}")
                        return None, False, None

            # Send requests
            tasks = []
            for i in range(num_requests):
                text = self.sample_texts[i % len(self.sample_texts)]
                task = asyncio.create_task(send_request(text, i))
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # Process results
            for latency, success, is_cache_hit in results:
                if success and latency is not None:
                    latencies.append(latency)
                    successful += 1
                    if is_cache_hit:
                        cache_hits += 1
                    else:
                        cache_misses += 1

        if not latencies:
            print(f"ERROR: No successful requests for batch_size={batch_size}")
            return BatchSizeResult(
                batch_size=batch_size,
                total_requests=num_requests,
                successful_requests=0,
                avg_latency=0,
                p50_latency=0,
                p95_latency=0,
                p99_latency=0,
                requests_per_second=0,
                cache_hit_rate=0
            )

        # Calculate metrics
        total_time = max(latencies)  # Approximate total time
        avg_latency = statistics.mean(latencies)
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        rps = successful / total_time if total_time > 0 else 0
        hit_rate = (cache_hits / successful * 100) if successful > 0 else 0

        print(f"\nResults for batch_size={batch_size}:")
        print(f"  Successful: {successful}/{num_requests}")
        print(f"  Avg Latency: {avg_latency:.4f}s")
        print(f"  P50 Latency: {p50:.4f}s")
        print(f"  P95 Latency: {p95:.4f}s")
        print(f"  P99 Latency: {p99:.4f}s")
        print(f"  Throughput: {rps:.2f} req/s")
        print(f"  Cache Hit Rate: {hit_rate:.1f}%")

        return BatchSizeResult(
            batch_size=batch_size,
            total_requests=num_requests,
            successful_requests=successful,
            avg_latency=avg_latency,
            p50_latency=p50,
            p95_latency=p95,
            p99_latency=p99,
            requests_per_second=rps,
            cache_hit_rate=hit_rate
        )

    def _update_env_batch_size(self, batch_size: int):
        """Update TEI_REQUEST_BATCH_SIZE in .env file"""
        env_path = ".env"
        with open(env_path, 'r') as f:
            lines = f.readlines()

        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith("TEI_REQUEST_BATCH_SIZE="):
                    f.write(f"TEI_REQUEST_BATCH_SIZE={batch_size}\n")
                else:
                    f.write(line)

        print(f"Updated .env: TEI_REQUEST_BATCH_SIZE={batch_size}")

    def _restart_cache_proxy(self):
        """Restart the cache proxy systemd service"""
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "cache-proxy.service"],
                check=True,
                capture_output=True,
                text=True
            )
            print("Cache proxy restarted successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to restart cache proxy: {e}")
            raise

    async def run_tuning(
        self,
        batch_sizes: List[int],
        num_requests: int = 100,
        concurrency: int = 20
    ) -> List[BatchSizeResult]:
        """Run tuning tests for multiple batch sizes"""
        results = []

        for batch_size in batch_sizes:
            result = await self.test_batch_size(
                batch_size,
                num_requests=num_requests,
                concurrency=concurrency
            )
            results.append(result)

            # Small delay between tests
            await asyncio.sleep(2)

        return results

    def print_summary(self, results: List[BatchSizeResult]):
        """Print summary of all batch size tests"""
        print(f"\n{'='*60}")
        print("BATCH SIZE TUNING SUMMARY")
        print(f"{'='*60}")
        print(f"{'Batch Size':<12} {'Avg Latency':<14} {'P95':<10} {'P99':<10} {'RPS':<10} {'Hit Rate':<10}")
        print("-" * 70)

        for r in results:
            print(
                f"{r.batch_size:<12} "
                f"{r.avg_latency:<14.4f} "
                f"{r.p95_latency:<10.4f} "
                f"{r.p99_latency:<10.4f} "
                f"{r.requests_per_second:<10.2f} "
                f"{r.cache_hit_rate:<10.1f}%"
            )

        print("-" * 70)

        # Find optimal batch size
        # Prioritize: 1) High throughput, 2) Low P95 latency, 3) High cache hit rate
        best_result = max(
            results,
            key=lambda r: (r.requests_per_second, -r.p95_latency, r.cache_hit_rate)
        )

        print(f"\nRECOMMENDED BATCH SIZE: {best_result.batch_size}")
        print(f"  Expected Throughput: {best_result.requests_per_second:.2f} req/s")
        print(f"  Expected P95 Latency: {best_result.p95_latency:.4f}s")
        print(f"  Expected Cache Hit Rate: {best_result.cache_hit_rate:.1f}%")

        # Update .env with optimal batch size
        self._update_env_batch_size(best_result.batch_size)
        print(f"\nUpdated .env with optimal batch size: {best_result.batch_size}")

        # Save results to JSON
        with open("batch_size_tuning_results.json", "w") as f:
            json.dump([r.__dict__ for r in results], f, indent=2)
        print(f"Results saved to batch_size_tuning_results.json")


def generate_sample_texts(count: int = 50) -> List[str]:
    """Generate sample texts for testing"""
    base_texts = [
        "This is a test sentence for embedding generation.",
        "Machine learning models process text data efficiently.",
        "Vector embeddings represent semantic meaning numerically.",
        "Cache optimization improves application performance significantly.",
        "Distributed systems require careful coordination.",
        "Natural language processing enables text understanding.",
        "Deep learning has revolutionized many fields.",
        "Real-time applications demand low latency responses.",
        "Batch processing improves throughput for embeddings.",
        "GPU acceleration speeds up model inference.",
    ]

    # Generate variations
    texts = []
    for i in range(count):
        base = base_texts[i % len(base_texts)]
        if i % 3 == 0:
            texts.append(base)
        elif i % 3 == 1:
            texts.append(base + f" Variation {i}.")
        else:
            texts.append(f"{i}. {base}")

    return texts


async def main():
    parser = argparse.ArgumentParser(
        description="Tune TEI_REQUEST_BATCH_SIZE for optimal performance"
    )
    parser.add_argument(
        "url",
        help="Cache proxy URL (e.g., http://localhost:8081/v1/embeddings)"
    )
    parser.add_argument(
        "-b",
        "--batch-sizes",
        type=int,
        nargs="+",
        default=[4, 8, 12, 16, 24, 32, 48, 64],
        help="Batch sizes to test (default: 4 8 12 16 24 32 48 64)"
    )
    parser.add_argument(
        "-r",
        "--requests",
        type=int,
        default=100,
        help="Number of requests per batch size (default: 100)"
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=20,
        help="Concurrent requests (default: 20)"
    )
    parser.add_argument(
        "-s",
        "--sample-count",
        type=int,
        default=50,
        help="Number of sample texts (default: 50)"
    )

    args = parser.parse_args()

    print(f"Batch Size Tuning for Cache Proxy")
    print(f"Target URL: {args.url}")
    print(f"Batch sizes to test: {args.batch_sizes}")
    print(f"Requests per size: {args.requests}")
    print(f"Concurrency: {args.concurrency}")

    # Generate sample texts
    sample_texts = generate_sample_texts(args.sample_count)
    print(f"Generated {len(sample_texts)} sample texts")

    # Run tuning
    tuner = BatchSizeTuner(args.url, sample_texts)
    results = await tuner.run_tuning(
        batch_sizes=args.batch_sizes,
        num_requests=args.requests,
        concurrency=args.concurrency
    )

    # Print summary
    tuner.print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
