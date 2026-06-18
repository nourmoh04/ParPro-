from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from products.models import Product, Stock
from orders.models import Order, OrderItem, Cart, CartItem, BatchJobRun, BatchChunkLog


class Command(BaseCommand):
    help = "Print a database summary for testing and discussion."

    def handle(self, *args, **options):
        self.stdout.write("========== DATABASE SUMMARY ==========")
        self.stdout.write(f"Users: {User.objects.count()}")
        self.stdout.write(f"Products: {Product.objects.count()}")
        self.stdout.write(f"Stock rows: {Stock.objects.count()}")
        self.stdout.write(f"Orders: {Order.objects.count()}")
        self.stdout.write(f"OrderItems: {OrderItem.objects.count()}")
        self.stdout.write(f"Carts: {Cart.objects.count()}")
        self.stdout.write(f"CartItems: {CartItem.objects.count()}")
        self.stdout.write(f"BatchJobRun: {BatchJobRun.objects.count()}")
        self.stdout.write(f"BatchChunkLog: {BatchChunkLog.objects.count()}")

        self.stdout.write("\n========== ORDER STATUS ==========")
        for row in Order.objects.values("status").annotate(count=Count("id")).order_by("status"):
            self.stdout.write(f"{row['status']}: {row['count']}")

        self.stdout.write("\n========== TOTAL SOLD QUANTITY ==========")
        total_quantity = OrderItem.objects.aggregate(total_quantity=Sum("quantity"))["total_quantity"] or 0
        self.stdout.write(f"Total sold quantity: {total_quantity}")

        self.stdout.write("\n========== FIRST 10 PRODUCTS ==========")
        for product in Product.objects.all().order_by("id")[:10]:
            stock = Stock.objects.filter(product=product).first()
            stock_quantity = stock.quantity if stock else None
            self.stdout.write(
                f"{product.id} | {product.name} | price={product.price} | stock={stock_quantity}"
            )

        self.stdout.write("\n========== TOP 10 POPULAR PRODUCTS ==========")
        popular_products = (
            OrderItem.objects
            .values("product_id", "product__name")
            .annotate(total_sold=Sum("quantity"), order_items=Count("id"))
            .order_by("-total_sold")[:10]
        )

        for row in popular_products:
            self.stdout.write(
                f"product_id={row['product_id']} | "
                f"name={row['product__name']} | "
                f"total_sold={row['total_sold']} | "
                f"order_items={row['order_items']}"
            )