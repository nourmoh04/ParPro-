import csv
import glob
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests


BASE_URL = "http://127.0.0.1:8000"
RESULTS_DIR = "results"
REQUESTS_COUNT = 100
MAX_WORKERS = 50


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def percentile(values, percent):
    if not values:
        return None

    sorted_values = sorted(values)
    index = int(round((percent / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]


def timed_get(path):
    url = f"{BASE_URL}{path}"
    start = time.perf_counter()

    try:
        response = requests.get(url, timeout=60)
        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        return {
            "path": path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "ok": response.status_code < 400,
            "payload_bytes": len(response.content),
            "error": None,
        }

    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        return {
            "path": path,
            "status_code": None,
            "duration_ms": duration_ms,
            "ok": False,
            "payload_bytes": 0,
            "error": str(exc),
        }


def warm_endpoint(path):
    result = timed_get(path)
    print(
        f"Warm-up {path}: status={result['status_code']}, "
        f"time={result['duration_ms']} ms, bytes={result['payload_bytes']}"
    )


def benchmark_endpoint(label, path):
    print("\n" + "═" * 70)
    print(label)
    print(path)
    print(f"{REQUESTS_COUNT} requests, max_workers={MAX_WORKERS}")
    print("═" * 70)

    start = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(timed_get, path)
            for _ in range(REQUESTS_COUNT)
        ]

        for future in as_completed(futures):
            results.append(future.result())

    elapsed_seconds = round(time.perf_counter() - start, 3)

    durations = [r["duration_ms"] for r in results]
    success_count = sum(1 for r in results if r["ok"])
    failed_count = len(results) - success_count
    payload_sizes = [r["payload_bytes"] for r in results if r["payload_bytes"] > 0]

    summary = {
        "label": label,
        "path": path,
        "requests_count": REQUESTS_COUNT,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate_percent": round((success_count / REQUESTS_COUNT) * 100, 2),
        "avg_ms": round(statistics.mean(durations), 3),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "min_ms": min(durations),
        "elapsed_seconds": elapsed_seconds,
        "throughput_requests_per_sec": round(REQUESTS_COUNT / elapsed_seconds, 3),
        "avg_payload_bytes": round(statistics.mean(payload_sizes), 2) if payload_sizes else 0,
        "max_payload_bytes": max(payload_sizes) if payload_sizes else 0,
    }

    print(f"Success:       {summary['success_count']}/{REQUESTS_COUNT}")
    print(f"Failed:        {summary['failed_count']}")
    print(f"Avg:           {summary['avg_ms']} ms")
    print(f"P95:           {summary['p95_ms']} ms")
    print(f"Max:           {summary['max_ms']} ms")
    print(f"Throughput:    {summary['throughput_requests_per_sec']} req/s")
    print(f"Avg payload:   {summary['avg_payload_bytes']} bytes")

    return summary, results


def load_latest_req9_summary():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "req9_stress_*.json")))
    if not files:
        return None

    latest_file = files[-1]

    with open(latest_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    return latest_file, data.get("summary", {})


def save_benchmark(summary, before_results, after_results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(RESULTS_DIR, f"req10_benchmark_{timestamp}.json")
    csv_path = os.path.join(RESULTS_DIR, f"req10_benchmark_{timestamp}.csv")

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    with open(csv_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "phase",
            "path",
            "status_code",
            "duration_ms",
            "ok",
            "payload_bytes",
            "error",
        ])

        for result in before_results:
            writer.writerow([
                "before_full_list",
                result["path"],
                result["status_code"],
                result["duration_ms"],
                result["ok"],
                result["payload_bytes"],
                result["error"],
            ])

        for result in after_results:
            writer.writerow([
                "after_paginated_list",
                result["path"],
                result["status_code"],
                result["duration_ms"],
                result["ok"],
                result["payload_bytes"],
                result["error"],
            ])

    return json_path, csv_path


def main():
    ensure_results_dir()

    latest_req9 = load_latest_req9_summary()

    print("\nRequirement #10: Benchmarking and Bottleneck Analysis")
    print("Bottleneck from Req #9: full product list endpoint returns the entire catalog.")

    if latest_req9:
        latest_file, req9_summary = latest_req9
        print(f"Loaded Req #9 summary from: {latest_file}")
        print(f"Req #9 p95 response time: {req9_summary.get('p95_response_ms')} ms")
        print(f"Req #9 slowest paths sample:")
        for row in req9_summary.get("slowest_paths", [])[:5]:
            print(
                f"  {row['path']} | count={row['count']} | "
                f"avg={row['avg_ms']} ms | p95={row['p95_ms']} ms"
            )

    before_path = "/products/list-cached/"
    after_path = "/products/list-paginated-cached/?page=1&page_size=100"

    print("\nWarm-up phase:")
    warm_endpoint(before_path)
    warm_endpoint(after_path)

    before_summary, before_results = benchmark_endpoint(
        "BEFORE: full cached product list",
        before_path,
    )

    after_summary, after_results = benchmark_endpoint(
        "AFTER: paginated cached product list",
        after_path,
    )

    avg_speedup = round(before_summary["avg_ms"] / after_summary["avg_ms"], 2)
    p95_speedup = round(before_summary["p95_ms"] / after_summary["p95_ms"], 2)
    payload_reduction = round(
        before_summary["avg_payload_bytes"] / after_summary["avg_payload_bytes"],
        2
    ) if after_summary["avg_payload_bytes"] > 0 else None

    final_summary = {
        "requirement": "Req10 Benchmarking and Bottleneck Analysis",
        "bottleneck": {
            "problem": "Full product list endpoint returns the whole catalog and becomes slow under stress.",
            "before_endpoint": before_path,
            "after_endpoint": after_path,
            "solution": "Use cached pagination to reduce response payload and serialization work.",
        },
        "before": before_summary,
        "after": after_summary,
        "comparison": {
            "avg_speedup": avg_speedup,
            "p95_speedup": p95_speedup,
            "payload_reduction_factor": payload_reduction,
        },
    }

    json_path, csv_path = save_benchmark(final_summary, before_results, after_results)

    print("\n" + "═" * 70)
    print("Requirement #10 Final Comparison")
    print("═" * 70)
    print(f"Before avg:         {before_summary['avg_ms']} ms")
    print(f"After avg:          {after_summary['avg_ms']} ms")
    print(f"Avg speedup:        {avg_speedup}x")
    print(f"Before p95:         {before_summary['p95_ms']} ms")
    print(f"After p95:          {after_summary['p95_ms']} ms")
    print(f"P95 speedup:        {p95_speedup}x")
    print(f"Payload reduction:  {payload_reduction}x")
    print(f"Saved JSON:         {json_path}")
    print(f"Saved CSV:          {csv_path}")
    print("═" * 70)

    if after_summary["avg_ms"] < before_summary["avg_ms"]:
        print("RESULT: Bottleneck improved after applying cached pagination.")
    else:
        print("WARNING: Improvement was not observed. Re-run benchmark or inspect logs.")


if __name__ == "__main__":
    main()