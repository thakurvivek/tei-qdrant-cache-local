#!/usr/bin/env python3
"""
Simple embedding workload generator for testing cache proxy.
Generates requests with varying cache hit ratios.
"""

import asyncio
import httpx
import time
import random
import argparse
from typing import List

# Sample texts for embedding
SAMPLE_TEXTS = [
    "hello world",
    "machine learning is awesome",
    "python programming language",
    "deep learning models",
    "neural networks",
    "artificial intelligence",
    "data science",
    "natural language processing",
    "computer vision",
    "reinforcement learning",
    "transformer architecture",
    "attention mechanism",
    "gradient descent",
    "backpropagation",
    "overfitting and underfitting",
    "cross-validation",
    "feature engineering",
    "model deployment",
    "hyperparameter tuning",
    "batch normalization",
]

class WorkloadGenerator:
    def __init__(self, url: str, cache_hit_ratio: float = 0.5):
        self.url = url
        self.cache_hit_ratio = cache_hit_ratio
        self.client = httpx.AsyncClient(timeout=60.0)
        self.cached_texts = set()

    async def send_request(self, text: str) -> dict:
        """Send a single embedding request."""
        start = time.monotonic()
        try:
            response = await self.client.post(
                self.url,
                json={"input": [text], "model": "octen-0.6b-fp16"},
                headers={"Content-Type": "application/json"}
            )
            latency = time.monotonic() - start
            success = response.status_code == 200
            
            # Detect cache hit based on latency (fast responses are likely cached)
            is_cache_hit = latency < 0.01
            
            return {
                "success": success,
                "latency": latency,
                "is_cache_hit": is_cache_hit,
                "status_code": response.status_code
            }
        except Exception as e:
            latency = time.monotonic() - start
            return {
                "success": False,
                "latency": latency,
                "is_cache_hit": False,
                "error": str(e)
            }

    async def run_workload(self, total_requests: int, concurrency: int = 10):
        """Run workload with specified parameters."""
        print(f"Starting workload: {total_requests} requests, concurrency={concurrency}")
        print(f"Target cache hit ratio: {self.cache_hit_ratio:.1%}")
        print(f"URL: {self.url}")
        print("-" * 50)

        results = []
        start_time = time.monotonic()

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_request(text: str):
            async with semaphore:
                return await self.send_request(text)

        # Generate requests
        tasks = []
        for i in range(total_requests):
            # Decide whether to use cached text or new text
            if random.random() < self.cache_hit_ratio and self.cached_texts:
                text = random.choice(list(self.cached_texts))
            else:
                text = random.choice(SAMPLE_TEXTS)
                self.cached_texts.add(text)

            tasks.append(bounded_request(text))

        # Execute all requests
        results = await asyncio.gather(*tasks)

        total_duration = time.monotonic() - start_time

        # Calculate statistics
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        cache_hits = sum(1 for r in successful if r["is_cache_hit"])
        cache_misses = len(successful) - cache_hits

        latencies = [r["latency"] for r in successful]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50_latency = sorted(latencies)[len(latencies)//2] if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies)*0.99)] if latencies else 0

        # Print results
        print("\n=== Workload Results ===")
        print(f"Total Duration:      {total_duration:.2f} s")
        print(f"Total Requests:      {total_requests}")
        print(f"Successful:          {len(successful)}")
        print(f"Failed:              {len(failed)}")
        print(f"Success Rate:        {len(successful)/total_requests*100:.2f}%")
        print(f"Cache Hits:          {cache_hits}")
        print(f"Cache Misses:        {cache_misses}")
        print(f"Cache Hit Rate:      {cache_hits/len(successful)*100:.2f}%")
        print(f"Requests/sec:        {total_requests/total_duration:.2f}")
        print(f"\nLatency (successful):")
        print(f"  Average:           {avg_latency*1000:.2f} ms")
        print(f"  P50:               {p50_latency*1000:.2f} ms")
        print(f"  P95:               {p95_latency*1000:.2f} ms")
        print(f"  P99:               {p99_latency*1000:.2f} ms")

        await self.client.aclose()

async def main():
    parser = argparse.ArgumentParser(description="Generate embedding workload")
    parser.add_argument("--url", default="http://localhost:8081/v1/embeddings",
                        help="Cache proxy URL")
    parser.add_argument("--requests", type=int, default=100,
                        help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Number of concurrent requests")
    parser.add_argument("--cache-hit-ratio", type=float, default=0.5,
                        help="Target cache hit ratio (0.0 to 1.0)")

    args = parser.parse_args()

    generator = WorkloadGenerator(args.url, args.cache_hit_ratio)
    await generator.run_workload(args.requests, args.concurrency)

if __name__ == "__main__":
    asyncio.run(main())
