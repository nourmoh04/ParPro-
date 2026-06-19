import time
import requests


BASE_URL = "http://127.0.0.1:8000"


def post(path):
    return requests.post(f"{BASE_URL}{path}", timeout=10)


def get(path):
    start = time.time()
    response = requests.get(f"{BASE_URL}{path}", timeout=10)
    duration = time.time() - start
    response.raise_for_status()
    return response.json(), duration


def print_result(label, data, measured_duration):
    print("----------------------------------------")
    print(label)
    print("----------------------------------------")
    print(f"Endpoint response time: {data.get('response_time_seconds')}s")
    print(f"Measured client time:   {measured_duration:.4f}s")
    print(f"Cache enabled:          {data.get('cache_enabled')}")
    print(f"Cache status:           {data.get('cache_status', 'N/A')}")
    print(f"Data source:            {data.get('data_source')}")
    print(f"Metrics:                {data.get('metrics')}")


def compare_product_list():
    print("\n=== PRODUCT LIST CACHE TEST ===")

    post("/products/cache-clear/")
    post("/products/cache-metrics/reset/")

    uncached, uncached_time = get("/products/list-uncached/")
    cached_miss, miss_time = get("/products/list-cached/")
    cached_hit, hit_time = get("/products/list-cached/")

    print_result("1) Uncached product list", uncached, uncached_time)
    print_result("2) Cached product list - first call (MISS)", cached_miss, miss_time)
    print_result("3) Cached product list - second call (HIT)", cached_hit, hit_time)

    if hit_time > 0:
        speedup = uncached_time / hit_time
    else:
        speedup = 0

    print(f"\nProduct list client-side speedup: {speedup:.2f}x")


def compare_product_detail(product_id=1):
    print("\n=== PRODUCT DETAIL CACHE TEST ===")

    post("/products/cache-clear/")
    post("/products/cache-metrics/reset/")

    uncached, uncached_time = get(f"/products/{product_id}/detail-uncached/")
    cached_miss, miss_time = get(f"/products/{product_id}/detail-cached/")
    cached_hit, hit_time = get(f"/products/{product_id}/detail-cached/")

    print_result("1) Uncached product detail", uncached, uncached_time)
    print_result("2) Cached product detail - first call (MISS)", cached_miss, miss_time)
    print_result("3) Cached product detail - second call (HIT)", cached_hit, hit_time)

    if hit_time > 0:
        speedup = uncached_time / hit_time
    else:
        speedup = 0

    print(f"\nProduct detail client-side speedup: {speedup:.2f}x")


def compare_popular_products():
    print("\n=== POPULAR PRODUCTS CACHE TEST ===")

    post("/products/cache-clear/")
    post("/products/cache-metrics/reset/")

    uncached, uncached_time = get("/products/popular-uncached/")
    cached_miss, miss_time = get("/products/popular-cached/")
    cached_hit, hit_time = get("/products/popular-cached/")

    print_result("1) Uncached popular products", uncached, uncached_time)
    print_result("2) Cached popular products - first call (MISS)", cached_miss, miss_time)
    print_result("3) Cached popular products - second call (HIT)", cached_hit, hit_time)

    if hit_time > 0:
        speedup = uncached_time / hit_time
    else:
        speedup = 0

    print(f"\nPopular products client-side speedup: {speedup:.2f}x")


def main():
    print("========================================")
    print("Requirement 6 - Distributed Caching Test")
    print("========================================")

    compare_product_list()
    compare_product_detail(product_id=1)
    compare_popular_products()

    print("\n========================================")
    print("Cache test completed.")
    print("Expected result: second cached request should be HIT and faster.")
    print("========================================")


if __name__ == "__main__":
    main()