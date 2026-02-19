#!/usr/bin/env python3
"""
Analyze stress test results and generate comparison reports
"""

import json
import argparse
import os
import glob
from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestSummary:
    """Summary of a single test result"""
    filename: str
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    rps: float
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    avg_latency: float
    p50_latency: float
    p90_latency: float
    p95_latency: float
    p99_latency: float
    total_duration: float
    cpu_start: float
    cpu_end: float
    memory_start_mb: float
    memory_end_mb: float


def load_result_file(filepath: str) -> Dict[str, Any]:
    """Load a JSON result file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def parse_test_summary(filepath: str, data: Dict[str, Any]) -> TestSummary:
    """Parse test data into a summary object"""
    filename = os.path.basename(filepath)
    test_name = filename.replace('.json', '').split('_')[-1]

    metrics = data.get('metrics', {})
    stats = data.get('statistics', {})
    system = data.get('system_metrics', {})

    return TestSummary(
        filename=filename,
        test_name=test_name,
        total_requests=metrics.get('total_requests', 0),
        successful_requests=metrics.get('successful_requests', 0),
        failed_requests=metrics.get('failed_requests', 0),
        success_rate=stats.get('success_rate', 0.0),
        rps=stats.get('rps', 0.0),
        cache_hits=metrics.get('cache_hits', 0),
        cache_misses=metrics.get('cache_misses', 0),
        cache_hit_rate=stats.get('cache_hit_rate', 0.0),
        avg_latency=stats.get('avg_latency', 0.0),
        p50_latency=stats.get('p50_latency', 0.0),
        p90_latency=stats.get('p90_latency', 0.0),
        p95_latency=stats.get('p95_latency', 0.0),
        p99_latency=stats.get('p99_latency', 0.0),
        total_duration=metrics.get('total_duration', 0.0),
        cpu_start=system.get('start', {}).get('cpu_percent', 0.0),
        cpu_end=system.get('end', {}).get('cpu_percent', 0.0),
        memory_start_mb=system.get('start', {}).get('memory_used_mb', 0.0),
        memory_end_mb=system.get('end', {}).get('memory_used_mb', 0.0),
    )


def print_comparison_table(summaries: List[TestSummary]):
    """Print a comparison table of all tests"""
    print("\n" + "=" * 120)
    print("STRESS TEST COMPARISON TABLE")
    print("=" * 120)

    # Header
    header = f"{'Test Name':<20} {'Reqs':>8} {'Success':>8} {'RPS':>8} {'Cache%':>8} {'Avg(ms)':>10} {'P50(ms)':>10} {'P90(ms)':>10} {'P95(ms)':>10} {'P99(ms)':>10}"
    print(header)
    print("-" * 120)

    # Rows
    for summary in summaries:
        row = (
            f"{summary.test_name:<20} "
            f"{summary.total_requests:>8} "
            f"{summary.success_rate:>7.1f}% "
            f"{summary.rps:>8.1f} "
            f"{summary.cache_hit_rate:>7.1f}% "
            f"{summary.avg_latency*1000:>9.2f} "
            f"{summary.p50_latency*1000:>9.2f} "
            f"{summary.p90_latency*1000:>9.2f} "
            f"{summary.p95_latency*1000:>9.2f} "
            f"{summary.p99_latency*1000:>9.2f}"
        )
        print(row)

    print("=" * 120)


def print_system_resources_table(summaries: List[TestSummary]):
    """Print system resource usage table"""
    print("\n" + "=" * 80)
    print("SYSTEM RESOURCE USAGE")
    print("=" * 80)

    header = f"{'Test Name':<20} {'CPU%':>10} {'CPU%':>10} {'Mem(MB)':>12} {'Mem(MB)':>12}"
    print(header)
    print(f"{'':<20} {'Start':>10} {'End':>10} {'Start':>12} {'End':>12}")
    print("-" * 80)

    for summary in summaries:
        row = (
            f"{summary.test_name:<20} "
            f"{summary.cpu_start:>9.1f} "
            f"{summary.cpu_end:>9.1f} "
            f"{summary.memory_start_mb:>11.1f} "
            f"{summary.memory_end_mb:>11.1f}"
        )
        print(row)

    print("=" * 80)


def print_best_performers(summaries: List[TestSummary]):
    """Print best performers in various categories"""
    print("\n" + "=" * 80)
    print("BEST PERFORMERS")
    print("=" * 80)

    if not summaries:
        return

    # Highest RPS
    best_rps = max(summaries, key=lambda x: x.rps)
    print(f"Highest Throughput (RPS):     {best_rps.test_name} ({best_rps.rps:.1f} RPS)")

    # Lowest Average Latency
    best_avg_latency = min(summaries, key=lambda x: x.avg_latency)
    print(f"Lowest Avg Latency:          {best_avg_latency.test_name} ({best_avg_latency.avg_latency*1000:.2f} ms)")

    # Lowest P99 Latency
    best_p99_latency = min(summaries, key=lambda x: x.p99_latency)
    print(f"Lowest P99 Latency:          {best_p99_latency.test_name} ({best_p99_latency.p99_latency*1000:.2f} ms)")

    # Highest Cache Hit Rate
    best_cache_hit = max(summaries, key=lambda x: x.cache_hit_rate)
    print(f"Highest Cache Hit Rate:      {best_cache_hit.test_name} ({best_cache_hit.cache_hit_rate:.1f}%)")

    # Highest Success Rate
    best_success_rate = max(summaries, key=lambda x: x.success_rate)
    print(f"Highest Success Rate:        {best_success_rate.test_name} ({best_success_rate.success_rate:.1f}%)")

    print("=" * 80)


def print_cache_analysis(summaries: List[TestSummary]):
    """Print cache performance analysis"""
    print("\n" + "=" * 80)
    print("CACHE PERFORMANCE ANALYSIS")
    print("=" * 80)

    # Group by cache hit rate ranges
    high_cache = [s for s in summaries if s.cache_hit_rate >= 70]
    medium_cache = [s for s in summaries if 30 <= s.cache_hit_rate < 70]
    low_cache = [s for s in summaries if s.cache_hit_rate < 30]

    print(f"\nHigh Cache Hit Rate (>=70%): {len(high_cache)} tests")
    if high_cache:
        avg_latency_high = sum(s.avg_latency for s in high_cache) / len(high_cache)
        print(f"  Average Latency: {avg_latency_high*1000:.2f} ms")

    print(f"\nMedium Cache Hit Rate (30-70%): {len(medium_cache)} tests")
    if medium_cache:
        avg_latency_medium = sum(s.avg_latency for s in medium_cache) / len(medium_cache)
        print(f"  Average Latency: {avg_latency_medium*1000:.2f} ms")

    print(f"\nLow Cache Hit Rate (<30%): {len(low_cache)} tests")
    if low_cache:
        avg_latency_low = sum(s.avg_latency for s in low_cache) / len(low_cache)
        print(f"  Average Latency: {avg_latency_low*1000:.2f} ms")

    print("\n" + "=" * 80)


def generate_markdown_report(summaries: List[TestSummary], output_file: str):
    """Generate a markdown report"""
    with open(output_file, 'w') as f:
        f.write("# Stress Test Results Report\n\n")
        f.write(f"Generated: {os.path.basename(output_file)}\n\n")

        f.write("## Test Comparison\n\n")
        f.write("| Test Name | Requests | Success Rate | RPS | Cache Hit % | Avg Latency (ms) | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) |\n")
        f.write("|-----------|----------|--------------|-----|-------------|------------------|----------|----------|----------|----------|\n")

        for s in summaries:
            f.write(f"| {s.test_name} | {s.total_requests} | {s.success_rate:.1f}% | {s.rps:.1f} | "
                   f"{s.cache_hit_rate:.1f}% | {s.avg_latency*1000:.2f} | {s.p50_latency*1000:.2f} | "
                   f"{s.p90_latency*1000:.2f} | {s.p95_latency*1000:.2f} | {s.p99_latency*1000:.2f} |\n")

        f.write("\n## System Resources\n\n")
        f.write("| Test Name | CPU Start % | CPU End % | Memory Start (MB) | Memory End (MB) |\n")
        f.write("|-----------|-------------|-----------|-------------------|----------------|\n")

        for s in summaries:
            f.write(f"| {s.test_name} | {s.cpu_start:.1f} | {s.cpu_end:.1f} | "
                   f"{s.memory_start_mb:.1f} | {s.memory_end_mb:.1f} |\n")

        f.write("\n## Key Findings\n\n")

        # Best performers
        best_rps = max(summaries, key=lambda x: x.rps)
        best_avg_latency = min(summaries, key=lambda x: x.avg_latency)
        best_p99_latency = min(summaries, key=lambda x: x.p99_latency)
        best_cache_hit = max(summaries, key=lambda x: x.cache_hit_rate)

        f.write(f"- **Highest Throughput**: {best_rps.test_name} ({best_rps.rps:.1f} RPS)\n")
        f.write(f"- **Lowest Avg Latency**: {best_avg_latency.test_name} ({best_avg_latency.avg_latency*1000:.2f} ms)\n")
        f.write(f"- **Lowest P99 Latency**: {best_p99_latency.test_name} ({best_p99_latency.p99_latency*1000:.2f} ms)\n")
        f.write(f"- **Highest Cache Hit Rate**: {best_cache_hit.test_name} ({best_cache_hit.cache_hit_rate:.1f}%)\n")

    print(f"\nMarkdown report saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze stress test results and generate comparison reports"
    )
    parser.add_argument(
        "results_dir",
        help="Directory containing stress test result JSON files",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output markdown report file",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.json",
        help="File pattern to match (default: *.json)",
    )

    args = parser.parse_args()

    # Find all result files
    pattern = os.path.join(args.results_dir, args.pattern)
    result_files = glob.glob(pattern)

    if not result_files:
        print(f"No result files found matching pattern: {pattern}")
        return

    print(f"Found {len(result_files)} result files")

    # Load and parse all results
    summaries = []
    for filepath in sorted(result_files):
        try:
            data = load_result_file(filepath)
            summary = parse_test_summary(filepath, data)
            summaries.append(summary)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")

    if not summaries:
        print("No valid results to analyze")
        return

    # Print reports
    print_comparison_table(summaries)
    print_system_resources_table(summaries)
    print_best_performers(summaries)
    print_cache_analysis(summaries)

    # Generate markdown report if requested
    if args.output:
        generate_markdown_report(summaries, args.output)


if __name__ == "__main__":
    main()
