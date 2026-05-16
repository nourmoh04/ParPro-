import json
import time

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

        # Artificial delay to increase the chance of Race Condition.
        # Many requests can read the same old stock value before saving.
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