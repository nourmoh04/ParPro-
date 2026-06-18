import sys
import time
import threading
import requests

BASE_URL      = "http://127.0.0.1:8000/orders"
THREADS_COUNT = 10


def send_request(thread_id, url, barrier, results):
    try:
        barrier.wait()  

        resp    = requests.post(url, timeout=30)
        body    = resp.json()
        status  = resp.status_code

        results.append({"thread": thread_id, "status": status, "body": body})

        if status == 200:
            t = body.get("processing_time_sec", "?")
            print(f"  Thread {thread_id:02d}:  JOB STARTED   |finish after {t}s")
        elif status == 423:
            ttl = body.get("lock_ttl_sec", "?")
            print(f"  Thread {thread_id:02d}:  LOCKED        | Lock finish after {ttl}s")
        else:
            print(f"  Thread {thread_id:02d}: Error  {status}     | {str(body)[:60]}")

    except Exception as e:
        results.append({"thread": thread_id, "status": "ERROR", "body": str(e)})
        print(f"  Thread {thread_id:02d}:  {e}")


def run_test(mode: str) -> dict:
    urls = {
        "unsafe": f"{BASE_URL}/run-sales-report-unsafe/",
        "safe":   f"{BASE_URL}/run-sales-report-safe/",
    }
    labels = {
        "unsafe": "BEFORE — No Lock       (All jobs run simultaneously) ",
        "safe":   "AFTER  — Redis Lock  (Only 1 job runs, others get 423)",
    }

    print(f"\n{'═'*60}")
    print(f"  Req #7: {labels[mode]}")
    print(f"  {urls[mode]}")
    print(f"  {THREADS_COUNT} threads in the same time")
    print(f"{'═'*60}\n")

    barrier = threading.Barrier(THREADS_COUNT)
    results = []
    threads = [
        threading.Thread(target=send_request, args=(i, urls[mode], barrier, results))
        for i in range(THREADS_COUNT)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    started = sum(1 for r in results if r["status"] == 200)
    locked  = sum(1 for r in results if r["status"] == 423)

    print(f"\n{'─'*60}")
    print(f"  Jobs running in parallel   : {started}")
    print(f"  Blocked by Redis Lock   : {locked}")

    if mode == "unsafe":
        if started > 1:
            print(f"\n  ISSUE DEMONSTRATED: {started} jobs are running at the same time")
        else:
            print(f"\n  Try again — maybe they didn't overlap")
    else:
        if started == 1 and locked == THREADS_COUNT - 1:
            print(f"\n  SOLUTION WORKING: Only 1 job started, {locked} blocked by Redis lock")
            print(f"    (This is a Distributed Lock, not a DB lock)")
        elif started == 0:
            print(f"\n  Lock is still held from a previous run — wait 60 seconds")

    print(f"{'═'*60}\n")
    return {"started": started, "locked": locked}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "all":
        print("\n Requirement #7: Distributed Lock — Before vs After\n")
        before = run_test("unsafe")
        print("  Waiting 6 seconds for jobs to finish..\n")
        time.sleep(6)
        after = run_test("safe")

        print("╔" + "═"*50 + "╗")
        print("║FINAL COMPARISON SUMMARY ║")
        print("╠" + "═"*50 + "╣")
        print(f"║  BEFORE │ Concurrent jobs : {before['started']:<3} │ No Lock      ║")
        print(f"║  AFTER  │ Concurrent jobs : {after['started']:<3} │ Redis lock      ║")
        print("╠" + "═"*50 + "╣")
        print("║  Req#1 used: select_for_update() ← DB lock  ║")
        print("║  Req#7 used: Redis lock ← distributed lock   ║")
        print("╚" + "═"*50 + "╝\n")
    else:
        run_test(mode)