import os, sys, threading, requests, django
from collections import Counter


os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ['no_proxy'] = '127.0.0.1,localhost'

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ParPro.settings")
django.setup()

from products.models import Product, Stock
from django.contrib.auth.models import User

BASE_URL = "http://127.0.0.1:8000/balancer"
THREADS_COUNT = 30
NO_PROXY = {"http": None, "https": None}


def prepare_data():
    User.objects.get_or_create(username="lb_test_user")
    product, _ = Product.objects.get_or_create(
        name="LB Test Product", defaults={"price": 10}
    )
    stock, _ = Stock.objects.get_or_create(
        product=product, defaults={"quantity": 500}
    )
    stock.quantity = 500
    stock.save()
    return product


def reset_balancer_stats():
    try:
        response = requests.post(
            f"{BASE_URL}/reset/",
            timeout=10,
            proxies=NO_PROXY,
        )
        print(f"Reset stats: {response.status_code} | {response.text}")
    except Exception as e:
        print(f"Reset stats failed: {e}")


def send_request(i, strategy, product_id, barrier, results):
    try:
        barrier.wait()
        response = requests.post(
            f"{BASE_URL}/route/",
            json={
                "strategy": strategy,
                "path": "/orders/place-order/",
                "payload": {"product_id": product_id, "quantity": 1},
            },
            timeout=15,
            proxies=NO_PROXY,  
        )
        data = response.json()
        routed_to = data.get("routed_to", "error")
        results.append(routed_to)
        print(f"Thread {i:02d} → {routed_to} | status: {response.status_code}")

    except Exception as e:
        print(f"Thread {i:02d}: ERROR - {e}")
        results.append("error")


def run_test(strategy):
    product = prepare_data()
    reset_balancer_stats()
    print(f"====================================")
    print(f"Strategy: {strategy.upper()} | Requests: {THREADS_COUNT}")
    print(f"====================================\n")

    barrier = threading.Barrier(THREADS_COUNT)
    results = []
    threads = [
        threading.Thread(
            target=send_request,
            args=(i, strategy, product.id, barrier, results)
        )
        for i in range(THREADS_COUNT)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    dist = Counter(results)
    print(f"====================================")
    print(f"DISTRIBUTION RESULT")
    print(f"====================================")
    for server, count in sorted(dist.items()):
        print(f"  {server}: {'█' * count} ({count} reqs - {round(count/THREADS_COUNT*100)}%)")

    counts = [v for k, v in dist.items() if k != "error"]
    print(f"\nRESULT: {'BALANCED ' if counts and max(counts)-min(counts) <= 3 else 'UNBALANCED '}")

    stats = requests.get(
        f"{BASE_URL}/stats/",
        proxies=NO_PROXY  
    ).json()
    print(f"Total handled: {stats['total_requests']}")
    print(f"====================================\n")


if __name__ == "__main__":
    run_test(sys.argv[1] if len(sys.argv) > 1 else "round_robin")