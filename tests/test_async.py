import os
import sys
import time
import threading
import requests
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ParPro.settings")
django.setup()

from django.contrib.auth.models import User
from products.models import Product, Stock


BASE_URL = "http://127.0.0.1:8000/orders"
THREADS_COUNT = 10
INITIAL_STOCK = 50
QUANTITY_PER_REQUEST = 1


def prepare_test_data():

    User.objects.get_or_create(username="async_test_user")

    product, _ = Product.objects.get_or_create(
        name="Async Test Product",
        defaults={"price": 50}
    )

    from orders.models import Order, OrderItem

    test_order_ids = OrderItem.objects.filter(
        product=product
    ).values_list("order_id", flat=True)

    Order.objects.filter(id__in=test_order_ids).delete()

    stock, _ = Stock.objects.get_or_create(
        product=product,
        defaults={"quantity": INITIAL_STOCK}
    )

    stock.quantity = INITIAL_STOCK
    stock.save()

    return product


def get_url_for_mode(mode):
    if mode == "sync":
        return f"{BASE_URL}/place-order-sync/"
    if mode == "async":
        return f"{BASE_URL}/place-order-async/"
    raise ValueError("Mode must be 'sync', 'async', or 'compare'")


def send_order(i, url, product_id, barrier, results):
    try:
        barrier.wait()
        start = time.time()

        response = requests.post(
            url,
            json={"product_id": product_id, "quantity": QUANTITY_PER_REQUEST},
            timeout=60,
        )

        elapsed = round(time.time() - start, 3)

        try:
            data = response.json()
        except ValueError:
            data = {"raw_response": response.text}

        ok = response.status_code == 200 and data.get("success") is True

        results.append({
            "thread": i,
            "ok": ok,
            "status_code": response.status_code,
            "response_time": elapsed,
            "server_time": data.get("response_time_seconds", "N/A"),
            "response": data,
        })

        print(
            f"Thread {i:02d}: status={response.status_code} | "
            f"client={elapsed}s | server={data.get('response_time_seconds', 'N/A')}s"
        )

    except Exception as e:
        results.append({
            "thread": i,
            "ok": False,
            "status_code": "ERROR",
            "response_time": -1,
            "server_time": "N/A",
            "response": str(e),
        })
        print(f"Thread {i:02d}: ERROR - {e}")


def wait_for_background_tasks(seconds=6):

    print(f"Waiting {seconds}s for background tasks to finish...")
    time.sleep(seconds)

    try:
        response = requests.get(f"{BASE_URL}/async-queue/status/", timeout=10)
        data = response.json()
        queue = data.get("queue", {})
        print("Queue status:")
        print(f"  worker_started    : {queue.get('worker_started')}")
        print(f"  queued_tasks      : {queue.get('queued_tasks')}")
        print(f"  total_logged_tasks: {queue.get('total_logged_tasks')}")

        tasks = queue.get("tasks", [])
        completed = sum(1 for task in tasks if task.get("status") == "completed")
        failed = sum(1 for task in tasks if task.get("status") == "failed")
        print(f"  completed in latest logs: {completed}")
        print(f"  failed in latest logs   : {failed}")

    except Exception as exc:
        print(f"Could not read queue status: {exc}")


def run_test(mode):
    url = get_url_for_mode(mode)
    product = prepare_test_data()

    print("\n====================================")
    print(f"Async Processing Test: {mode.upper()}")
    print(f"URL: {url}")
    print(f"Concurrent requests: {THREADS_COUNT}")
    print(f"Initial stock: {INITIAL_STOCK}")
    print("====================================\n")

    barrier = threading.Barrier(THREADS_COUNT)
    results = []

    threads = [
        threading.Thread(
            target=send_order,
            args=(i, url, product.id, barrier, results)
        )
        for i in range(THREADS_COUNT)
    ]

    total_start = time.time()

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    total_elapsed = round(time.time() - total_start, 3)

    success = [result for result in results if result["ok"]]
    failed = THREADS_COUNT - len(success)

    response_times = [
        result["response_time"]
        for result in success
        if result["response_time"] >= 0
    ]

    avg_time = round(sum(response_times) / len(response_times), 3) if response_times else 0
    min_time = min(response_times) if response_times else 0
    max_time = max(response_times) if response_times else 0

    print("\n====================================")
    print("TEST RESULT")
    print("====================================")
    print(f"Mode                 : {mode.upper()}")
    print(f"Successful requests  : {len(success)}/{THREADS_COUNT}")
    print(f"Failed requests      : {failed}")
    print(f"Average response time: {avg_time}s")
    print(f"Min response time    : {min_time}s")
    print(f"Max response time    : {max_time}s")
    print(f"Total test time      : {total_elapsed}s")

    if mode == "sync":
        print("Result meaning       : user waits for email + invoice before response")
    else:
        print("Result meaning       : email + invoice are queued and processed in background")

    print("====================================\n")

    if mode == "async":
        wait_for_background_tasks()

    return {
        "mode": mode,
        "success": len(success),
        "failed": failed,
        "avg_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "total_time": total_elapsed,
    }


def run_comparison():
    sync_result = run_test("sync")
    async_result = run_test("async")

    speedup = 0
    if async_result["avg_time"] > 0:
        speedup = round(sync_result["avg_time"] / async_result["avg_time"], 2)

    print("\n====================================")
    print("SYNC VS ASYNC COMPARISON")
    print("====================================")
    print(f"Sync avg response time : {sync_result['avg_time']}s")
    print(f"Async avg response time: {async_result['avg_time']}s")
    print(f"Response speedup       : {speedup}x")
    print(f"Sync total test time   : {sync_result['total_time']}s")
    print(f"Async total test time  : {async_result['total_time']}s")
    print("====================================")


if __name__ == "__main__":
    mode = "compare"

    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

    if mode == "compare":
        run_comparison()
    elif mode in ["sync", "async"]:
        run_test(mode)
    else:
        print("Usage:")
        print("  python test_async.py")
        print("  python test_async.py compare")
        print("  python test_async.py sync")
        print("  python test_async.py async")
        sys.exit(1)
