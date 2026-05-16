import json
import time
import threading 

from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

from products.models import Stock
from .models import Order, OrderItem


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

def _send_confirmation_email(order_id):
    time.sleep(2)  
    print(f" [BACKGROUND] Email sent for Order #{order_id}")


def _generate_invoice(order_id):
    time.sleep(3) 
    print(f" [BACKGROUND] Invoice generated for Order #{order_id}")


def _run_in_background(func, *args):
    thread = threading.Thread(target=func, args=args)
    thread.daemon = True
    thread.start()

@csrf_exempt
def place_order_unsafe(request):
    """
    UNSAFE endpoint:
    This endpoint intentionally does NOT use transaction.atomic()
    and does NOT use select_for_update().

    It is used only to demonstrate Race Condition / Lost Update
    under concurrent requests.
    """
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
            order=order,
            product_id=product_id,
            quantity=qty,
            price=product_price,
        )

        return JsonResponse({
            "success": True,
            "mode": "unsafe",
            "order_id": order.id,
            "remaining_stock": stock.quantity,
        })

    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)

    except Exception as e:
        return JsonResponse({
            "error": "Something went wrong on the server",
            "details": str(e),
        }, status=500)


@csrf_exempt
def place_order(request):
    """
    SAFE endpoint:
    This endpoint uses transaction.atomic() and select_for_update()
    to lock the stock row while updating it.

    This prevents concurrent requests from modifying the same stock
    record at the same time.
    """
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
                order=order,
                product_id=product_id,
                quantity=qty,
                price=product_price,
            )

        return JsonResponse({
            "success": True,
            "mode": "safe",
            "order_id": order.id,
        })

    except Exception as e:
        return JsonResponse({
            "error": "Something went wrong on the server",
            "details": str(e),
        }, status=500)
    
@csrf_exempt
def place_order_sync(request):
    """
    SYNCHRONOUS endpoint (BEFORE):
    The user waits for ALL tasks to complete:
    - Save order to DB
    - Send confirmation email     (2 seconds)
    - Generate invoice PDF        (3 seconds)
    Total wait: ~5+ seconds
    """
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
                order=order,
                product_id=product_id,
                quantity=qty,
                price=product_price,
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
            "note": "User waited for email + invoice before getting response"
        })

    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



@csrf_exempt
def place_order_async(request):
    """
    ASYNCHRONOUS endpoint (AFTER):
    User gets immediate response after saving order.
    Heavy tasks run in background:
    - Send confirmation email     (background thread)
    - Generate invoice PDF        (background thread)
    Total wait: ~0.05 seconds
    """
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
                order=order,
                product_id=product_id,
                quantity=qty,
                price=product_price,
            )

        _run_in_background(_send_confirmation_email, order.id)
        _run_in_background(_generate_invoice, order.id)

        total_time = round(time.time() - start, 3)

        return JsonResponse({
            "success": True,
            "mode": "async",
            "order_id": order.id,
            "response_time_seconds": total_time,
            "note": "Email and invoice processing in background"
        })

    except Stock.DoesNotExist:
        return JsonResponse({"error": "Product or Stock not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
