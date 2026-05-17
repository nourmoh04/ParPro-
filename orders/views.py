import json
import time
import threading
import queue        

from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

from products.models import Stock
from .models import Order, OrderItem



task_queue = queue.Queue()   


def worker():
    print(" [WORKER] Queue Worker started and waiting for tasks...")
    while True:
        try:
            func, args = task_queue.get(timeout=1)
            print(f" [WORKER] Picked up task: {func.__name__}")
            func(*args)
            task_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f" [WORKER] Task failed: {e}")
            task_queue.task_done()


worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()


def enqueue_task(func, *args):
    task_queue.put((func, args))
    print(f" [QUEUE] Task added: {func.__name__} | Queue size: {task_queue.qsize()}")



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
                order=order, product_id=product_id,
                quantity=qty, price=product_price,
            )
        start = time.time()
        _send_confirmation_email(order.id)
        _generate_invoice(order.id)
        total_time = round(time.time() - start, 3)
        return JsonResponse({
            "success": True,
            "mode": "sync",
            "order_id": order.id,
            "response_time_seconds": total_time,
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
    parsed, error_response = _parse_order_request(request)
    if error_response:
        return error_response
    product_id, qty = parsed
    user = _get_test_user()
    if not user:
        return JsonResponse({"error": "No users found"}, status=400)
    try:
        start = time.time()
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(product_id=product_id)
            if stock.quantity < qty:
                return JsonResponse({"error": "Not enough stock!"}, status=400)
            stock.quantity -= qty
            stock.save()
            product_price = stock.product.price
            order = Order.objects.create(user=user, total=product_price * qty)
            OrderItem.objects.create(
                order=order, product_id=product_id,
                quantity=qty, price=product_price,
            )

        enqueue_task(_send_confirmation_email, order.id)
        enqueue_task(_generate_invoice, order.id)

        total_time = round(time.time() - start, 3)
        return JsonResponse({
            "success": True,
            "mode": "async",
            "order_id": order.id,
            "response_time_seconds": total_time,
            "queue_size": task_queue.qsize(),
            "note": "Tasks queued - processed by background worker"
        })
    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)