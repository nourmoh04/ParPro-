import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis
import requests


BASE_URL = "http://127.0.0.1:8000"
LOCK_KEY = "lock:daily_sales_job"


def get_thread_count():
    if len(sys.argv) < 2:
        return 10

    try:
        value = int(sys.argv[1])
        if value <= 0:
            raise ValueError
        return value
    except ValueError:
        print("Invalid thread count. Example: python test_distributed_lock.py 50")
        sys.exit(1)


THREADS = get_thread_count()


redis_client = redis.Redis(
    host="127.0.0.1",
    port=6379,
    db=0,
    decode_responses=True,
)


def clear_redis_lock():
    redis_client.delete(LOCK_KEY)


def post_request(thread_id, endpoint):
    url = f"{BASE_URL}{endpoint}"
    start = time.time()

    try:
        response = requests.post(url, timeout=90)
        duration = time.time() - start

        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        return {
            "thread_id": thread_id,
            "status_code": response.status_code,
            "duration": duration,
            "data": data,
        }

    except Exception as exc:
        duration = time.time() - start
        return {
            "thread_id": thread_id,
            "status_code": None,
            "duration": duration,
            "data": {"error": str(exc)},
        }


def run_concurrent_test(title, endpoint):
    print("\n")
    print("═" * 70)
    print(title)
    print(f"{BASE_URL}{endpoint}")
    print(f"{THREADS} threads at the same time")
    print("═" * 70)

    results = []

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [
            executor.submit(post_request, thread_id, endpoint)
            for thread_id in range(THREADS)
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            thread_id = result["thread_id"]
            status_code = result["status_code"]
            duration = result["duration"]
            data = result["data"]

            if status_code == 423:
                ttl = data.get("lock_ttl_sec")
                print(
                    f"  Thread {thread_id:02d}: LOCKED      | "
                    f"Redis lock refused request (TTL remaining: {ttl}s)"
                )
            elif status_code == 200:
                workload = data.get("database_workload", {})
                completed_orders = workload.get("completed_orders", "N/A")
                order_items = workload.get("order_items_processed", "N/A")

                print(
                    f"  Thread {thread_id:02d}: JOB STARTED | "
                    f"finish after {duration:.2f}s | "
                    f"orders={completed_orders} | items={order_items}"
                )
            else:
                print(
                    f"  Thread {thread_id:02d}: ERROR       | "
                    f"status={status_code} | data={data}"
                )

    started_jobs = sum(1 for r in results if r["status_code"] == 200)
    locked_jobs = sum(1 for r in results if r["status_code"] == 423)
    failed_jobs = THREADS - started_jobs - locked_jobs

    return {
        "started_jobs": started_jobs,
        "locked_jobs": locked_jobs,
        "failed_jobs": failed_jobs,
        "results": results,
    }


def print_summary(label, summary):
    print("\n" + "─" * 70)
    print(label)
    print("─" * 70)
    print(f"Jobs started            : {summary['started_jobs']}")
    print(f"Blocked by Redis Lock   : {summary['locked_jobs']}")
    print(f"Failed / unexpected     : {summary['failed_jobs']}")


def main():
    print("\nRequirement #7: Distributed Lock — Before vs After")
    print(f"Configured concurrent requests: {THREADS}")

    clear_redis_lock()

    before = run_concurrent_test(
        "Req #7 BEFORE — No Lock (all jobs can run simultaneously)",
        "/orders/run-sales-report-unsafe/",
    )

    print_summary("BEFORE RESULT", before)
    print(f"\nISSUE DEMONSTRATED: {before['started_jobs']} jobs started at the same time.")

    print("\nWaiting 6 seconds for unsafe jobs to finish...")
    time.sleep(6)

    clear_redis_lock()

    after = run_concurrent_test(
        "Req #7 AFTER — Redis Distributed Lock (only one job should run)",
        "/orders/run-sales-report-safe/",
    )

    print_summary("AFTER RESULT", after)

    expected_locked = THREADS - 1

    print("\n" + "═" * 70)
    print("FINAL COMPARISON SUMMARY")
    print("═" * 70)
    print(f"BEFORE | Concurrent jobs started : {before['started_jobs']} | No lock")
    print(f"AFTER  | Concurrent jobs started : {after['started_jobs']} | Redis lock")
    print(f"AFTER  | Requests blocked        : {after['locked_jobs']} | Expected: {expected_locked}")
    print("Req#1 used: select_for_update()  <- Database lock")
    print("Req#7 used: Redis SET NX EX      <- Distributed lock")
    print("═" * 70)

    if after["started_jobs"] == 1 and after["locked_jobs"] == expected_locked:
        print("SOLUTION WORKING: Redis lock allowed exactly one job and blocked the rest.")
    else:
        print("WARNING: Result differs from expectation. Check Redis lock behavior.")


if __name__ == "__main__":
    main()