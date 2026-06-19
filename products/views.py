import time
import threading

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator

from products.models import Product, Stock
from orders.models import OrderItem


CACHE_TTL = getattr(settings, "CACHE_TTL_SECONDS", 60)

cache_metrics_lock = threading.Lock()

cache_metrics = {
    "product_list_hits": 0,
    "product_list_misses": 0,

    "product_detail_hits": 0,
    "product_detail_misses": 0,

    "popular_products_hits": 0,
    "popular_products_misses": 0,

    "database_reads": 0,
}


def _increase_metric(key):
    with cache_metrics_lock:
        cache_metrics[key] += 1


def _get_metrics_snapshot():
    with cache_metrics_lock:
        return dict(cache_metrics)


def _simulate_expensive_database_read(seconds=0.15):
    time.sleep(seconds)


def _serialize_product(product, stock_quantity=None):
    data = {
        "id": product.id,
        "name": product.name,
        "price": float(product.price),
    }

    if stock_quantity is not None:
        data["stock_quantity"] = stock_quantity

    return data


def _load_product_list_from_database():
    _increase_metric("database_reads")
    _simulate_expensive_database_read()

    stocks_by_product_id = {
        stock.product_id: stock.quantity
        for stock in Stock.objects.select_related("product").all()
    }

    products = Product.objects.all().order_by("id")

    return [
        _serialize_product(
            product,
            stock_quantity=stocks_by_product_id.get(product.id, 0)
        )
        for product in products
    ]


def _load_product_detail_from_database(product_id):
    _increase_metric("database_reads")
    _simulate_expensive_database_read()

    product = Product.objects.get(id=product_id)
    stock = Stock.objects.filter(product_id=product_id).first()

    return _serialize_product(
        product,
        stock_quantity=stock.quantity if stock else 0
    )


def _load_popular_products_from_database(limit=5):
    _increase_metric("database_reads")
    _simulate_expensive_database_read(seconds=0.25)

    rows = (
        OrderItem.objects
        .values("product_id", "product__name", "product__price")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:limit]
    )

    return [
        {
            "product_id": row["product_id"],
            "name": row["product__name"],
            "price": float(row["product__price"]),
            "total_sold": row["total_sold"],
        }
        for row in rows
    ]


def product_list_uncached(request):
    start = time.time()

    products = _load_product_list_from_database()

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "product-list-uncached",
        "cache_enabled": False,
        "data_source": "database",
        "response_time_seconds": response_time,
        "count": len(products),
        "products": products,
        "metrics": _get_metrics_snapshot(),
    })


def product_list_cached(request):
    start = time.time()

    cache_key = "products:list:v1"
    products = cache.get(cache_key)

    if products is None:
        _increase_metric("product_list_misses")
        products = _load_product_list_from_database()
        cache.set(cache_key, products, timeout=CACHE_TTL)
        data_source = "database_cache_miss"
        cache_status = "MISS"
    else:
        _increase_metric("product_list_hits")
        data_source = "redis_cache"
        cache_status = "HIT"

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "product-list-cached",
        "cache_enabled": True,
        "cache_status": cache_status,
        "data_source": data_source,
        "cache_key": cache_key,
        "cache_ttl_seconds": CACHE_TTL,
        "response_time_seconds": response_time,
        "count": len(products),
        "products": products,
        "metrics": _get_metrics_snapshot(),
    })


def product_detail_uncached(request, product_id):
    start = time.time()

    try:
        product = _load_product_detail_from_database(product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "product-detail-uncached",
        "cache_enabled": False,
        "data_source": "database",
        "response_time_seconds": response_time,
        "product": product,
        "metrics": _get_metrics_snapshot(),
    })


def product_detail_cached(request, product_id):
    start = time.time()

    cache_key = f"products:detail:{product_id}:v1"
    product = cache.get(cache_key)

    if product is None:
        _increase_metric("product_detail_misses")
        try:
            product = _load_product_detail_from_database(product_id)
        except Product.DoesNotExist:
            return JsonResponse({"error": "Product not found"}, status=404)

        cache.set(cache_key, product, timeout=CACHE_TTL)
        data_source = "database_cache_miss"
        cache_status = "MISS"
    else:
        _increase_metric("product_detail_hits")
        data_source = "redis_cache"
        cache_status = "HIT"

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "product-detail-cached",
        "cache_enabled": True,
        "cache_status": cache_status,
        "data_source": data_source,
        "cache_key": cache_key,
        "cache_ttl_seconds": CACHE_TTL,
        "response_time_seconds": response_time,
        "product": product,
        "metrics": _get_metrics_snapshot(),
    })


def popular_products_uncached(request):
    start = time.time()

    popular_products = _load_popular_products_from_database()

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "popular-products-uncached",
        "cache_enabled": False,
        "data_source": "database",
        "response_time_seconds": response_time,
        "count": len(popular_products),
        "popular_products": popular_products,
        "metrics": _get_metrics_snapshot(),
    })


def popular_products_cached(request):
    start = time.time()

    cache_key = "products:popular:v1"
    popular_products = cache.get(cache_key)

    if popular_products is None:
        _increase_metric("popular_products_misses")
        popular_products = _load_popular_products_from_database()
        cache.set(cache_key, popular_products, timeout=CACHE_TTL)
        data_source = "database_cache_miss"
        cache_status = "MISS"
    else:
        _increase_metric("popular_products_hits")
        data_source = "redis_cache"
        cache_status = "HIT"

    response_time = round(time.time() - start, 4)

    return JsonResponse({
        "success": True,
        "endpoint": "popular-products-cached",
        "cache_enabled": True,
        "cache_status": cache_status,
        "data_source": data_source,
        "cache_key": cache_key,
        "cache_ttl_seconds": CACHE_TTL,
        "response_time_seconds": response_time,
        "count": len(popular_products),
        "popular_products": popular_products,
        "metrics": _get_metrics_snapshot(),
    })


def cache_metrics_view(request):
    return JsonResponse({
        "success": True,
        "cache_backend": "Redis-compatible Memurai via django-redis",
        "cache_ttl_seconds": CACHE_TTL,
        "metrics": _get_metrics_snapshot(),
    })


@csrf_exempt
def reset_cache_metrics(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    with cache_metrics_lock:
        for key in cache_metrics:
            cache_metrics[key] = 0

    return JsonResponse({
        "success": True,
        "message": "Cache metrics reset successfully.",
        "metrics": _get_metrics_snapshot(),
    })


@csrf_exempt
def clear_product_cache(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    cache.delete("products:list:v1")
    cache.delete("products:popular:v1")

    product_ids = Product.objects.values_list("id", flat=True)
    for product_id in product_ids:
        cache.delete(f"products:detail:{product_id}:v1")

    return JsonResponse({
        "success": True,
        "message": "Product cache keys cleared successfully."
    })


def _positive_int_query_param(request, name, default, min_value=1, max_value=100):
    try:
        value = int(request.GET.get(name, default))
    except (TypeError, ValueError):
        value = default

    if value < min_value:
        value = min_value

    if value > max_value:
        value = max_value

    return value


def product_list_paginated_cached(request):
    start = time.time()

    page = _positive_int_query_param(
        request,
        "page",
        default=1,
        min_value=1,
        max_value=10_000,
    )

    page_size = _positive_int_query_param(
        request,
        "page_size",
        default=100,
        min_value=1,
        max_value=100,
    )

    cache_key = f"products:list:paginated:v1:page:{page}:size:{page_size}"
    cache_ttl = getattr(settings, "CACHE_TTL_SECONDS", 60)

    cached_payload = cache.get(cache_key)

    if cached_payload is not None:
        payload = dict(cached_payload)
        payload["response_time_seconds"] = round(time.time() - start, 4)
        payload["cache_status"] = "HIT"
        payload["data_source"] = "redis_cache"
        return JsonResponse(payload)

    products_qs = Product.objects.order_by("id")
    paginator = Paginator(products_qs, page_size)
    page_obj = paginator.get_page(page)

    product_ids = [product.id for product in page_obj.object_list]

    stock_by_product_id = {
        stock.product_id: stock.quantity
        for stock in Stock.objects.filter(product_id__in=product_ids)
    }

    products_data = [
        {
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "stock_quantity": stock_by_product_id.get(product.id, 0),
        }
        for product in page_obj.object_list
    ]

    payload = {
        "success": True,
        "cache_enabled": True,
        "cache_status": "MISS",
        "data_source": "database_cache_miss",
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_products": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "products": products_data,
    }

    cache.set(cache_key, payload, timeout=cache_ttl)

    payload["response_time_seconds"] = round(time.time() - start, 4)

    return JsonResponse(payload)