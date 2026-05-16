import os
import sys
import threading
import requests
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ParPro.settings")
django.setup()

from django.contrib.auth.models import User
from products.models import Product, Stock


BASE_URL = "http://127.0.0.1:8000/orders"

THREADS_COUNT = 50
INITIAL_STOCK = 10
QUANTITY_PER_REQUEST = 1


def prepare_test_data():
    User.objects.get_or_create(username="race_test_user")

    product, _ = Product.objects.get_or_create(
        name="Race Test Product",
        defaults={"price": 100}
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

        response = requests.post(
            url,
            json={
                "product_id": product_id,
                "quantity": QUANTITY_PER_REQUEST,
            },
            timeout=20,
        )

        response.encoding = "utf-8"

        ok = response.status_code == 200 and response.json().get("success") is True

        results.append({
            "thread": i,
            "status": response.status_code,
            "ok": ok,
            "response": response.text,
        })

        print(f"Thread {i:02d}: Status {response.status_code} | {response.text}")

    except Exception as e:
        results.append({
            "thread": i,
            "status": "ERROR",
            "ok": False,
            "response": str(e),
        })

        print(f"Thread {i:02d}: ERROR - {e}")


def run_test(mode):
    if mode == "unsafe":
        url = f"{BASE_URL}/place-order-unsafe/"
    elif mode == "safe":
        url = f"{BASE_URL}/place-order/"
    else:
        raise ValueError("Mode must be either 'unsafe' or 'safe'")

    product, stock = prepare_test_data()

    print("\n====================================")
    print(f"Running Race Condition Test: {mode.upper()}")
    print(f"URL: {url}")
    print(f"Product ID: {product.id}")
    print(f"Initial stock: {INITIAL_STOCK}")
    print(f"Concurrent requests: {THREADS_COUNT}")
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

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    stock.refresh_from_db()

    success_count = sum(1 for r in results if r["ok"])
    failed_count = THREADS_COUNT - success_count

    expected_stock = INITIAL_STOCK - success_count

    print("\n====================================")
    print("TEST RESULT")
    print("====================================")
    print(f"Mode: {mode}")
    print(f"Successful orders: {success_count}")
    print(f"Failed orders: {failed_count}")
    print(f"Expected final stock: {expected_stock}")
    print(f"Actual final stock: {stock.quantity}")

    if stock.quantity == expected_stock:
        print("RESULT: CONSISTENT ✅")
    else:
        print("RESULT: RACE CONDITION / LOST UPDATE DETECTED ❌")

    print("====================================\n")


if __name__ == "__main__":
    mode = "unsafe"

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    run_test(mode)
