import csv
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import django
import requests


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ParPro.settings")
django.setup()


from django.contrib.auth.models import User
from products.models import Product, Stock
from orders.models import Order, OrderItem, UserWallet


BASE_URL = "http://127.0.0.1:8000"
RESULTS_DIR = "results"
USERS_COUNT = 100
MAX_WORKERS = 100
CHECKOUT_QUANTITY = 1
WALLET_BALANCE = 10000


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def prepare_existing_data():
    """
    Uses existing final seed data.
    It does not create artificial products.
    It only creates or tops up wallets because UserWallet was introduced later.
    """
    users = list(
        User.objects
        .filter(username__startswith="final_user_")
        .order_by("id")[:USERS_COUNT]
    )

    if len(users) < USERS_COUNT:
        raise RuntimeError(
            f"Not enough final users. Required {USERS_COUNT}, found {len(users)}."
        )

    stocks = list(
        Stock.objects
        .select_related("product")
        .filter(
            product__name__startswith="Final Product ",
            quantity__gte=10,
            product__price__lte=WALLET_BALANCE,
        )
        .order_by("-quantity")[:50]
    )

    if len(stocks) < 10:
        raise RuntimeError(
            f"Not enough existing products with enough stock. Found {len(stocks)}."
        )

    for user in users:
        wallet, _ = UserWallet.objects.get_or_create(
            user=user,
            defaults={"balance": WALLET_BALANCE}
        )
        if wallet.balance < WALLET_BALANCE:
            wallet.balance = WALLET_BALANCE
            wallet.save(update_fields=["balance", "updated_at"])

    selected_products = [stock.product for stock in stocks]

    return users, selected_products


def timed_request(method, path, **kwargs):
    url = f"{BASE_URL}{path}"
    start = time.perf_counter()

    try:
        response = requests.request(method, url, timeout=60, **kwargs)
        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:300]}

        return {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "ok": response.status_code < 400,
            "body": body,
            "error": None,
        }

    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        return {
            "method": method,
            "path": path,
            "status_code": None,
            "duration_ms": duration_ms,
            "ok": False,
            "body": None,
            "error": str(exc),
        }


def warm_cache(product_id):
    """
    Warm-up phase. Real systems usually have hot product data in cache.
    The measured stress phase starts after this.
    """
    timed_request("GET", "/products/list-cached/")
    timed_request("GET", f"/products/{product_id}/detail-cached/")
    timed_request("GET", "/products/popular-cached/")


def run_user_journey(user, product):
    """
    One realistic e-commerce user journey:
    1. product list
    2. product detail
    3. popular products
    4. safe checkout
    """
    journey_results = []

    journey_results.append(
        timed_request("GET", "/products/list-cached/")
    )

    journey_results.append(
        timed_request("GET", f"/products/{product.id}/detail-cached/")
    )

    journey_results.append(
        timed_request("GET", "/products/popular-cached/")
    )

    journey_results.append(
        timed_request(
            "POST",
            "/orders/checkout-safe/",
            json={
                "username": user.username,
                "product_id": product.id,
                "quantity": CHECKOUT_QUANTITY,
                "force_failure": False,
            },
        )
    )

    return {
        "username": user.username,
        "product_id": product.id,
        "steps": journey_results,
    }


def percentile(values, percent):
    if not values:
        return None

    sorted_values = sorted(values)
    index = int(round((percent / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]


def summarize(results, started_at, finished_at):
    all_steps = []
    for result in results:
        all_steps.extend(result["steps"])

    durations = [step["duration_ms"] for step in all_steps]
    total_requests = len(all_steps)

    success_requests = sum(1 for step in all_steps if step["ok"])
    failed_requests = total_requests - success_requests

    status_counts = {}
    path_stats = {}

    for step in all_steps:
        status_key = str(step["status_code"])
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        path = step["path"]
        path_stats.setdefault(path, [])
        path_stats[path].append(step["duration_ms"])

    path_summary = []
    for path, values in path_stats.items():
        path_summary.append({
            "path": path,
            "count": len(values),
            "avg_ms": round(statistics.mean(values), 3),
            "p95_ms": percentile(values, 95),
            "max_ms": max(values),
        })

    path_summary.sort(key=lambda row: row["avg_ms"], reverse=True)

    checkout_steps = [
        step for step in all_steps
        if step["path"] == "/orders/checkout-safe/"
    ]

    checkout_success = sum(1 for step in checkout_steps if step["status_code"] == 200)
    checkout_failed = len(checkout_steps) - checkout_success

    elapsed_seconds = round(finished_at - started_at, 3)
    throughput = round(total_requests / elapsed_seconds, 3) if elapsed_seconds > 0 else None

    return {
        "requirement": "Req9 Stress Testing",
        "users_count": USERS_COUNT,
        "total_requests": total_requests,
        "success_requests": success_requests,
        "failed_requests": failed_requests,
        "success_rate_percent": round((success_requests / total_requests) * 100, 2),
        "checkout_success": checkout_success,
        "checkout_failed": checkout_failed,
        "avg_response_ms": round(statistics.mean(durations), 3),
        "p95_response_ms": percentile(durations, 95),
        "max_response_ms": max(durations),
        "elapsed_seconds": elapsed_seconds,
        "throughput_requests_per_sec": throughput,
        "status_counts": status_counts,
        "slowest_paths": path_summary,
    }


def save_results(summary, results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(RESULTS_DIR, f"req9_stress_{timestamp}.json")
    csv_path = os.path.join(RESULTS_DIR, f"req9_stress_{timestamp}.csv")

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "summary": summary,
                "results": results,
            },
            file,
            indent=2,
            ensure_ascii=False,
        )

    with open(csv_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "username",
            "product_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "ok",
            "error",
        ])

        for result in results:
            for step in result["steps"]:
                writer.writerow([
                    result["username"],
                    result["product_id"],
                    step["method"],
                    step["path"],
                    step["status_code"],
                    step["duration_ms"],
                    step["ok"],
                    step["error"],
                ])

    return json_path, csv_path


def print_summary(summary, json_path, csv_path):
    print("\n" + "═" * 70)
    print("Requirement #9: Stress Test Summary")
    print("═" * 70)
    print(f"Users:                     {summary['users_count']}")
    print(f"Total requests:            {summary['total_requests']}")
    print(f"Successful requests:       {summary['success_requests']}")
    print(f"Failed requests:           {summary['failed_requests']}")
    print(f"Success rate:              {summary['success_rate_percent']}%")
    print(f"Checkout success:          {summary['checkout_success']}")
    print(f"Checkout failed:           {summary['checkout_failed']}")
    print(f"Average response time:     {summary['avg_response_ms']} ms")
    print(f"P95 response time:         {summary['p95_response_ms']} ms")
    print(f"Max response time:         {summary['max_response_ms']} ms")
    print(f"Throughput:                {summary['throughput_requests_per_sec']} req/s")
    print(f"Status counts:             {summary['status_counts']}")
    print("\nSlowest paths:")
    for row in summary["slowest_paths"]:
        print(
            f"  {row['path']} | count={row['count']} | "
            f"avg={row['avg_ms']} ms | p95={row['p95_ms']} ms | max={row['max_ms']} ms"
        )
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}")
    print("═" * 70)


def main():
    ensure_results_dir()

    users, products = prepare_existing_data()

    print("\nRequirement #9: Stress Testing")
    print(f"Using existing final seed data: {len(users)} users and {len(products)} products.")
    print("Each user performs: list products, product detail, popular products, safe checkout.")

    warm_cache(products[0].id)

    started_at = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []

        for index, user in enumerate(users):
            product = products[index % len(products)]
            futures.append(executor.submit(run_user_journey, user, product))

        for future in as_completed(futures):
            results.append(future.result())

    finished_at = time.perf_counter()

    summary = summarize(results, started_at, finished_at)
    json_path, csv_path = save_results(summary, results)
    print_summary(summary, json_path, csv_path)

    if summary["failed_requests"] == 0:
        print("RESULT: System handled 100 concurrent users without request failures.")
    else:
        print("RESULT: Some requests failed. Analyze status codes and slowest paths for Req #10.")


if __name__ == "__main__":
    main()