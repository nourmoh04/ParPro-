import json
import time
import threading
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from .distributed_lock import DistributedLock, redis_client


from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

from products.models import Stock, Product
from .models import Order, OrderItem, UserWallet
from .async_queue import enqueue_task, get_queue_status


def _send_confirmation_email(order_id):
    time.sleep(2)
    print(f" [WORKER] Email sent for Order #{order_id}")


def _generate_invoice(order_id):
    time.sleep(3)
    print(f" [WORKER] Invoice generated for Order #{order_id}")


def _parse_order_request(request):
    try:
        data = json.loads(request.body)
        product_id = int(data["product_id"])
        qty = int(data["quantity"])
        if qty <= 0:
            return None, JsonResponse({"error": "Quantity must be greater than 0"}, status=400)
        return (product_id, qty), None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None, JsonResponse({"error": "Invalid data provided"}, status=400)


def _get_test_user():
    return User.objects.first()


@csrf_exempt
def place_order_unsafe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    parsed, error_response = _parse_order_request(request)
    if error_response:
        return error_response
    product_id, qty = parsed
    user = _get_test_user()
    if not user:
        return JsonResponse({"error": "No users found in system"}, status=400)
    try:
        stock = Stock.objects.get(product_id=product_id)
        if stock.quantity < qty:
            return JsonResponse({"error": "Not enough stock!"}, status=400)
        time.sleep(0.2)
        stock.quantity -= qty
        stock.save()
        product_price = stock.product.price
        order_total = product_price * qty
        order = Order.objects.create(user=user, total=order_total)
        OrderItem.objects.create(
            order=order, product_id=product_id,
            quantity=qty, price=product_price,
        )
        return JsonResponse({
            "success": True, "mode": "unsafe",
            "order_id": order.id, "remaining_stock": stock.quantity,
        })
    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": "Something went wrong", "details": str(e)}, status=500)


@csrf_exempt
def place_order(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    parsed, error_response = _parse_order_request(request)
    if error_response:
        return error_response
    product_id, qty = parsed
    user = _get_test_user()
    if not user:
        return JsonResponse({"error": "No users found in system"}, status=400)
    try:
        with transaction.atomic():
            try:
                stock = Stock.objects.select_for_update().get(product_id=product_id)
            except Stock.DoesNotExist:
                return JsonResponse({"error": "Product or Stock not found"}, status=404)
            if stock.quantity < qty:
                return JsonResponse({"error": "Not enough stock!"}, status=400)
            stock.quantity -= qty
            stock.save()
            product_price = stock.product.price
            order_total = product_price * qty
            order = Order.objects.create(user=user, total=order_total)
            OrderItem.objects.create(
                order=order, product_id=product_id,
                quantity=qty, price=product_price,
            )
        return JsonResponse({"success": True, "mode": "safe", "order_id": order.id})
    except Exception as e:
        return JsonResponse({"error": "Something went wrong", "details": str(e)}, status=500)



@csrf_exempt
def place_order_sync(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    start = time.time()

    parsed, error_response = _parse_order_request(request)
    if error_response:
        return error_response

    product_id, qty = parsed
    user = _get_test_user()

    if not user:
        return JsonResponse({"error": "No users found"}, status=400)

    try:
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(product_id=product_id)

            if stock.quantity < qty:
                return JsonResponse({"error": "Not enough stock!"}, status=400)

            stock.quantity -= qty
            stock.save()

            product_price = stock.product.price
            order = Order.objects.create(user=user, total=product_price * qty)

            OrderItem.objects.create(
                order=order,
                product_id=product_id,
                quantity=qty,
                price=product_price,
            )

        _send_confirmation_email(order.id)
        _generate_invoice(order.id)

        response_time = round(time.time() - start, 3)

        return JsonResponse({
            "success": True,
            "mode": "sync",
            "message": "Order created. Email and invoice were processed before response.",
            "order_id": order.id,
            "response_time_seconds": response_time,
            "note": "User waited for email + invoice"
        })

    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def place_order_async(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    start = time.time()

    parsed, error_response = _parse_order_request(request)
    if error_response:
        return error_response

    product_id, qty = parsed
    user = _get_test_user()

    if not user:
        return JsonResponse({"error": "No users found"}, status=400)

    try:
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(product_id=product_id)

            if stock.quantity < qty:
                return JsonResponse({"error": "Not enough stock!"}, status=400)

            stock.quantity -= qty
            stock.save()

            product_price = stock.product.price
            order = Order.objects.create(user=user, total=product_price * qty)

            OrderItem.objects.create(
                order=order,
                product_id=product_id,
                quantity=qty,
                price=product_price,
            )

        email_task_id = enqueue_task(
            "send_confirmation_email",
            _send_confirmation_email,
            order.id
        )

        invoice_task_id = enqueue_task(
            "generate_invoice",
            _generate_invoice,
            order.id
        )

        response_time = round(time.time() - start, 3)

        return JsonResponse({
            "success": True,
            "mode": "async",
            "message": "Order created. Email and invoice tasks were queued.",
            "order_id": order.id,
            "response_time_seconds": response_time,
            "queued_tasks": {
                "email_task_id": email_task_id,
                "invoice_task_id": invoice_task_id,
            },
            "note": "Tasks queued and processed by background worker"
        })

    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def async_queue_status_view(request):
    return JsonResponse({
        "success": True,
        "queue": get_queue_status(),
    })


PAYMENT_SIMULATION_SECONDS = 5
PAYMENT_POOL_WORKERS = 5
PAYMENT_MEMORY_MB = 30
PAYMENT_CPU_SECONDS = 0.8

payment_executor = ThreadPoolExecutor(max_workers=PAYMENT_POOL_WORKERS)

payment_metrics_lock = threading.Lock()

payment_metrics = {
    "uncontrolled_active": 0,
    "uncontrolled_max_active": 0,
    "uncontrolled_total_requests": 0,

    "controlled_active": 0,
    "controlled_max_active": 0,
    "controlled_total_requests": 0,
}

def _consume_cpu_for_seconds(seconds):
    end_time = time.time() + seconds
    checksum = 0

    while time.time() < end_time:
        for i in range(10_000):
            checksum += (i * i) % 97

    return checksum


def _simulate_payment_processing(mode):

    active_key = f"{mode}_active"
    max_key = f"{mode}_max_active"
    total_key = f"{mode}_total_requests"

    with payment_metrics_lock:
        payment_metrics[total_key] += 1
        payment_metrics[active_key] += 1

        if payment_metrics[active_key] > payment_metrics[max_key]:
            payment_metrics[max_key] = payment_metrics[active_key]

        current_active = payment_metrics[active_key]

    simulated_memory = bytearray(PAYMENT_MEMORY_MB * 1024 * 1024)

    for i in range(0, len(simulated_memory), 4096):
        simulated_memory[i] = i % 256

    time.sleep(PAYMENT_SIMULATION_SECONDS)

    checksum = _consume_cpu_for_seconds(PAYMENT_CPU_SECONDS)

    with payment_metrics_lock:
        payment_metrics[active_key] -= 1

    return {
        "payment_status": "success",
        "mode": mode,
        "active_payment_tasks_when_started": current_active,
        "simulation_seconds": PAYMENT_SIMULATION_SECONDS,
        "simulated_memory_mb_per_task": PAYMENT_MEMORY_MB,
        "simulated_cpu_seconds": PAYMENT_CPU_SECONDS,
        "checksum": checksum,
    }


@csrf_exempt
def process_payment_uncontrolled(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    start = time.time()

    result = _simulate_payment_processing("uncontrolled")

    response_time = round(time.time() - start, 3)

    return JsonResponse({
        "success": True,
        "endpoint": "process-payment-uncontrolled",
        "resource_management": "disabled",
        "response_time_seconds": response_time,
        "result": result,
        "metrics": {
            "total_requests": payment_metrics["uncontrolled_total_requests"],
            "max_active_payment_tasks": payment_metrics["uncontrolled_max_active"],
        }
    })


@csrf_exempt
def process_payment_controlled(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    start = time.time()

    future = payment_executor.submit(_simulate_payment_processing, "controlled")
    result = future.result()

    response_time = round(time.time() - start, 3)

    return JsonResponse({
        "success": True,
        "endpoint": "process-payment-controlled",
        "resource_management": "enabled",
        "thread_pool_workers": PAYMENT_POOL_WORKERS,
        "response_time_seconds": response_time,
        "result": result,
        "metrics": {
            "total_requests": payment_metrics["controlled_total_requests"],
            "max_active_payment_tasks": payment_metrics["controlled_max_active"],
        }
    })


@csrf_exempt
def reset_payment_metrics(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    with payment_metrics_lock:
        for key in payment_metrics:
            payment_metrics[key] = 0

    return JsonResponse({
        "success": True,
        "message": "Payment metrics reset successfully"
    })


def payment_metrics_view(request):
    with payment_metrics_lock:
        metrics_snapshot = dict(payment_metrics)

    return JsonResponse({
        "success": True,
        "payment_pool_workers": PAYMENT_POOL_WORKERS,
        "payment_simulation_seconds": PAYMENT_SIMULATION_SECONDS,
        "metrics": metrics_snapshot,
    })

def _run_heavy_sales_job() -> dict:
    from django.db.models import Count, Sum
    from orders.models import Order, OrderItem

    job_start = time.time()

    completed_orders = Order.objects.filter(status="completed")

    order_stats = completed_orders.aggregate(
        completed_orders=Count("id"),
        total_revenue=Sum("total"),
    )

    item_stats = OrderItem.objects.filter(order__status="completed").aggregate(
        order_items_processed=Count("id"),
        total_quantity_sold=Sum("quantity"),
    )

    top_products = list(
        OrderItem.objects
        .filter(order__status="completed")
        .values("product_id", "product__name")
        .annotate(total_sold=Sum("quantity"), order_items=Count("id"))
        .order_by("-total_sold")[:5]
    )

    time.sleep(4)

    return {
        "job": "daily_sales_report",
        "job_status": "completed",
        "database_workload": {
            "completed_orders": order_stats["completed_orders"] or 0,
            "order_items_processed": item_stats["order_items_processed"] or 0,
            "total_quantity_sold": item_stats["total_quantity_sold"] or 0,
            "total_revenue": float(order_stats["total_revenue"] or 0),
            "top_products_sample": top_products,
        },
        "processing_time_sec": round(time.time() - job_start, 2),
        "finished_at": time.strftime("%H:%M:%S"),
    }

@csrf_exempt
def run_sales_report_unsafe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    result = _run_heavy_sales_job()

    return JsonResponse({
        "success": True,
        "mode": "unsafe",
        "lock_used": False,
        "lock_acquired": None,
        "job_status": "started_without_lock",
        "warning": "No lock is used. Multiple servers can run this job simultaneously.",
        **result,
    })


@csrf_exempt
def run_sales_report_safe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    lock = DistributedLock("daily_sales_job", timeout=60)

    if not lock.acquire():
        return JsonResponse({
            "success": False,
            "mode": "safe",
            "lock_used": True,
            "lock_acquired": False,
            "job_status": "blocked_by_redis_lock",
            "message": "Job is already running on another server.",
            "lock_key": "lock:daily_sales_job",
            "lock_type": "Redis Distributed Lock — NOT a database lock",
            "lock_ttl_sec": lock.ttl(),
        }, status=423)

    try:
        result = _run_heavy_sales_job()

        return JsonResponse({
            "success": True,
            "mode": "safe",
            "lock_used": True,
            "lock_acquired": True,
            "job_status": "started_with_redis_lock",
            "lock_key": "lock:daily_sales_job",
            "lock_type": "Redis Distributed Lock — NOT a database lock",
            **result,
        })

    finally:
        lock.release()


def distributed_lock_status(request):
    lock_key = "lock:daily_sales_job"
    locked = redis_client.exists(lock_key) == 1

    return JsonResponse({
        "success": True,
        "lock_key": lock_key,
        "lock_type": "Redis Distributed Lock — NOT a database lock",
        "is_locked": locked,
        "ttl_sec": redis_client.ttl(lock_key) if locked else None,
    })


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _money(value):
    return Decimal(str(value))


def _wallet_value(wallet):
    return float(wallet.balance) if wallet else None


@csrf_exempt
def acid_test_setup(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    data = _json_body(request)

    users_count = int(data.get("users", 50))
    stock_quantity = int(data.get("stock", 20))
    wallet_balance = _money(data.get("wallet_balance", "1000.00"))
    product_price = _money(data.get("product_price", "50.00"))
    product_name = data.get("product_name", "ACID Transaction Product")

    with transaction.atomic():
        acid_users = User.objects.filter(
            Q(username="acid_single_user") |
            Q(username__startswith="acid_user_")
        )

        acid_products = Product.objects.filter(name__startswith="ACID")

        OrderItem.objects.filter(order__user__in=acid_users).delete()
        Order.objects.filter(user__in=acid_users).delete()
        UserWallet.objects.filter(user__in=acid_users).delete()
        acid_users.delete()

        Stock.objects.filter(product__in=acid_products).delete()
        acid_products.delete()

        product = Product.objects.create(
            name=product_name,
            price=product_price
        )

        Stock.objects.create(
            product=product,
            quantity=stock_quantity
        )

        single_user = User.objects.create_user(
            username="acid_single_user",
            email="acid_single_user@example.com",
            password="test123"
        )

        UserWallet.objects.create(
            user=single_user,
            balance=wallet_balance
        )

        created_users = [single_user.username]

        for i in range(1, users_count + 1):
            username = f"acid_user_{i:03d}"
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="test123"
            )
            UserWallet.objects.create(
                user=user,
                balance=wallet_balance
            )
            created_users.append(username)

    return JsonResponse({
        "success": True,
        "message": "ACID test data prepared.",
        "product": {
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "stock": stock_quantity,
        },
        "single_user": "acid_single_user",
        "concurrent_users": users_count,
        "wallet_balance": float(wallet_balance),
        "note": "Only ACID test data was reset. Final seed data and old requirements data were not touched.",
    })


def acid_state(request):
    product_name = request.GET.get("product_name", "ACID Transaction Product")

    product = Product.objects.filter(name=product_name).first()
    if not product:
        return JsonResponse({
            "success": False,
            "error": "ACID product not found. Run /orders/acid/setup/ first."
        }, status=404)

    stock = Stock.objects.filter(product=product).first()

    acid_users = User.objects.filter(
        Q(username="acid_single_user") |
        Q(username__startswith="acid_user_")
    )

    wallets = UserWallet.objects.filter(user__in=acid_users)

    wallet_distribution = []
    for row in (
        wallets
        .values("balance")
        .annotate(count=Count("id"))
        .order_by("balance")
    ):
        wallet_distribution.append({
            "balance": float(row["balance"]),
            "count": row["count"],
        })

    orders = Order.objects.filter(user__in=acid_users)
    order_items = OrderItem.objects.filter(order__in=orders)

    single_user = User.objects.filter(username="acid_single_user").first()
    single_wallet = None
    if single_user:
        single_wallet = UserWallet.objects.filter(user=single_user).first()

    return JsonResponse({
        "success": True,
        "product": {
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "stock_quantity": stock.quantity if stock else None,
        },
        "single_user": {
            "username": "acid_single_user",
            "wallet_balance": _wallet_value(single_wallet),
            "orders_count": orders.filter(user=single_user).count() if single_user else 0,
        },
        "acid_users_count": acid_users.count(),
        "wallet_distribution": wallet_distribution,
        "orders_count": orders.count(),
        "completed_orders_count": orders.filter(status="completed").count(),
        "order_items_count": order_items.count(),
        "total_order_quantity": order_items.aggregate(total=Sum("quantity"))["total"] or 0,
        "total_order_value": float(orders.aggregate(total=Sum("total"))["total"] or 0),
    })


def _perform_checkout(
    username,
    product_id,
    quantity,
    force_failure=False,
    use_transaction=False,
):

    user = User.objects.get(username=username)

    if use_transaction:
        wallet = UserWallet.objects.select_for_update().get(user=user)
        stock = Stock.objects.select_for_update().select_related("product").get(product_id=product_id)
    else:
        wallet = UserWallet.objects.get(user=user)
        stock = Stock.objects.select_related("product").get(product_id=product_id)

    product = stock.product
    total = product.price * quantity

    if wallet.balance < total:
        return {
            "ok": False,
            "status": 400,
            "payload": {
                "success": False,
                "error": "Insufficient wallet balance",
                "wallet_balance": float(wallet.balance),
                "required": float(total),
            }
        }

    if stock.quantity < quantity:
        return {
            "ok": False,
            "status": 400,
            "payload": {
                "success": False,
                "error": "Insufficient stock",
                "available_stock": stock.quantity,
                "requested_quantity": quantity,
            }
        }

    wallet.balance -= total
    wallet.save(update_fields=["balance", "updated_at"])

    stock.quantity -= quantity
    stock.save(update_fields=["quantity"])

    if force_failure:
        raise RuntimeError("Forced failure after wallet and stock update, before order creation.")

    order = Order.objects.create(
        user=user,
        status="completed",
        total=total
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=quantity,
        price=product.price
    )

    return {
        "ok": True,
        "status": 200,
        "payload": {
            "success": True,
            "order_id": order.id,
            "username": username,
            "product_id": product.id,
            "quantity": quantity,
            "total": float(total),
            "remaining_wallet_balance": float(wallet.balance),
            "remaining_stock": stock.quantity,
        }
    }


@csrf_exempt
def checkout_unsafe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    data = _json_body(request)

    username = data.get("username", "acid_single_user")
    product_id = int(data["product_id"])
    quantity = int(data.get("quantity", 1))
    force_failure = bool(data.get("force_failure", False))

    try:
        result = _perform_checkout(
            username=username,
            product_id=product_id,
            quantity=quantity,
            force_failure=force_failure,
            use_transaction=False,
        )

        result["payload"].update({
            "mode": "unsafe",
            "transaction_used": False,
            "warning": "No transaction is used. A mid-operation failure can leave partial updates."
        })

        return JsonResponse(result["payload"], status=result["status"])

    except Exception as exc:
        return JsonResponse({
            "success": False,
            "mode": "unsafe",
            "transaction_used": False,
            "error": str(exc),
            "inconsistency_risk": True,
            "message": "Failure happened outside transaction. Previous wallet/stock updates may remain saved."
        }, status=500)


@csrf_exempt
def checkout_safe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    data = _json_body(request)

    username = data.get("username", "acid_single_user")
    product_id = int(data["product_id"])
    quantity = int(data.get("quantity", 1))
    force_failure = bool(data.get("force_failure", False))

    try:
        with transaction.atomic():
            result = _perform_checkout(
                username=username,
                product_id=product_id,
                quantity=quantity,
                force_failure=force_failure,
                use_transaction=True,
            )

            if not result["ok"]:
                return JsonResponse({
                    **result["payload"],
                    "mode": "safe",
                    "transaction_used": True,
                    "rollback_needed": False,
                    "message": "Request failed before any update was applied."
                }, status=result["status"])

        result["payload"].update({
            "mode": "safe",
            "transaction_used": True,
            "row_locks_used": ["UserWallet", "Stock"],
            "message": "Wallet, stock, order, and order item were committed together."
        })

        return JsonResponse(result["payload"], status=result["status"])

    except Exception as exc:
        return JsonResponse({
            "success": False,
            "mode": "safe",
            "transaction_used": True,
            "rollback_applied": True,
            "error": str(exc),
            "message": "Failure happened inside transaction.atomic(); wallet, stock, and order changes were rolled back."
        }, status=500)