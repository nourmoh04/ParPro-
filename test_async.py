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
INITIAL_STOCK = 20


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

    return product, stock


def send_order(i, url, product_id, barrier, results):
    try:
        barrier.wait()
        start = time.time()

        response = requests.post(
            url,
            json={"product_id": product_id, "quantity": 1},
            timeout=30,
        )

        elapsed = round(time.time() - start, 3)
        data = response.json()

        results.append({
            "thread": i,
            "ok": response.status_code == 200,
            "response_time": elapsed,
            "server_time": data.get("response_time_seconds", "N/A"),
        })

        print(f"Thread {i:02d}:  {elapsed}s | server: {data.get('response_time_seconds')}s")

    except Exception as e:
        results.append({"thread": i, "ok": False, "response_time": -1})
        print(f"Thread {i:02d}:  ERROR - {e}")


def run_test(mode):
    if mode == "sync":
        url = f"{BASE_URL}/place-order-sync/"
    elif mode == "async":
        url = f"{BASE_URL}/place-order-async/"
    else:
        raise ValueError("Mode must be 'sync' or 'async'")

    product, stock = prepare_test_data()

    print("\n====================================")
    print(f"Async Processing Test: {mode.upper()}")
    print(f"Threads: {THREADS_COUNT}")
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
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total_elapsed = round(time.time() - total_start, 3)

    success = [r for r in results if r["ok"]]
    avg_time = round(
        sum(r["response_time"] for r in success) / len(success), 3
    ) if success else 0

    print("\n====================================")
    print("TEST RESULT")
    print("====================================")
    print(f"Mode              : {mode.upper()}")
    print(f"Successful orders : {len(success)}/{THREADS_COUNT}")
    print(f"Avg response time : {avg_time}s per request")
    print(f"Total test time   : {total_elapsed}s")

    if mode == "sync":
        print(" User waited  (slow)")
    else:
        print(" ran in background  (fast)")

    print("====================================\n")
    print(" Background tasks still running (check server terminal)...")


if __name__ == "__main__":
    mode = "async"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    run_test(mode)