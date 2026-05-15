import json
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from products.models import Stock
from .models import Order, OrderItem

@csrf_exempt
def place_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    # 1. تحليل البيانات أولاً خارج الـ Transaction لتوفير وقت الاتصال بقاعدة البيانات
    try:
        data = json.loads(request.body)
        product_id = data['product_id']
        qty = int(data['quantity']) # التأكد من أنه رقم صحيح
        if qty <= 0:
            return JsonResponse({'error': 'Quantity must be greater than 0'}, status=400)
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Invalid data provided'}, status=400)

    # استخدام مستخدم تجريبي مؤقتاً (يفضل request.user مستقبلاً)
    user = User.objects.first()
    if not user:
        return JsonResponse({'error': 'No users found in system'}, status=400)

    try:
        # 2. بدء المعاملة الآمنة
        with transaction.atomic():
            try:
                # جلب المخزون وقفله فوراً
                stock = Stock.objects.select_for_update().get(product_id=product_id)
            except Stock.DoesNotExist:
                return JsonResponse({'error': 'Product or Stock not found'}, status=404)

            # التحقق من وفرة المخزون
            if stock.quantity < qty:
                return JsonResponse({'error': 'Not enough stock!'}, status=400)

            # خصم الكمية والحفظ
            stock.quantity -= qty
            stock.save()

            # فرضاً أن نموذج Stock يحتوي على سعر المنتج، أو قم بجلبه من نموذج المنتج
            product_price = getattr(stock.product, 'price', 100) # افتراض السعر 100 إذا لم يوجد
            order_total = product_price * qty

            # إنشاء الطلب وعناصره بالقيم الحقيقية
            order = Order.objects.create(user=user, total=order_total)
            OrderItem.objects.create(
                order=order, 
                product_id=product_id, 
                quantity=qty, 
                price=product_price
            )

        return JsonResponse({'success': True, 'order_id': order.id})

    except Exception as e:
        # أي خطأ غير متوقع هنا سيعيد كود 500 ويقوم بعمل Rollback تلقائي للمعاملة
        return JsonResponse({'error': 'Something went wrong on the server', 'details': str(e)}, status=500)
