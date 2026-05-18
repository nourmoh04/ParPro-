import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

from products.models import Stock
from .models import Order, OrderItem
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
    """
    Requirement 3 - BEFORE asynchronous queue:
    The request waits until email sending and invoice generation finish.
    """
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
    """
    Requirement 3 - AFTER asynchronous queue:
    The order is created quickly, while email and invoice tasks
    are added to the internal background queue.
    """
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
    """
    Returns the internal async queue status and latest task logs.
    """
    return JsonResponse({
        "success": True,
        "queue": get_queue_status(),
    })


# ============================================================
# Requirement 2: Resource Management & Capacity Control
# Payment processing simulation with and without Thread Pool
# ============================================================

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
    """
    Simulates a short CPU workload.

    This is intentionally limited to a small duration so the laptop
    remains safe during testing.
    """
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
    """
    BEFORE resource management:
    Every incoming request executes the simulated payment directly.

    Under high concurrency, many heavy payment operations may run at the same time.
    """
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
    """
    AFTER resource management:
    Payment operations are executed through a ThreadPoolExecutor.

    The pool limits the number of concurrently running payment tasks.
    Extra requests wait until a worker becomes available.
    """
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
    """
    Resets payment metrics before running a new resource-management test.
    """
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
    """
    Returns current payment resource-management metrics.
    """
    with payment_metrics_lock:
        metrics_snapshot = dict(payment_metrics)

    return JsonResponse({
        "success": True,
        "payment_pool_workers": PAYMENT_POOL_WORKERS,
        "payment_simulation_seconds": PAYMENT_SIMULATION_SECONDS,
        "metrics": metrics_snapshot,
    })