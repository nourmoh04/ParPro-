import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from products.models import Product, Stock
from orders.models import Order, OrderItem, Cart, CartItem


class Command(BaseCommand):
    help = "Seed a large e-commerce dataset for requirements 6 to 10."

    def add_arguments(self, parser):
        parser.add_argument(
            "--users",
            type=int,
            default=100,
            help="Number of test users to create."
        )
        parser.add_argument(
            "--products",
            type=int,
            default=300,
            help="Number of test products to create."
        )
        parser.add_argument(
            "--orders",
            type=int,
            default=5000,
            help="Number of completed/pending orders to create."
        )
        parser.add_argument(
            "--carts",
            type=int,
            default=80,
            help="Number of carts with cart items to create."
        )
        parser.add_argument(
            "--reset-final-data",
            action="store_true",
            help="Delete only final-seed data before recreating it."
        )

    def handle(self, *args, **options):
        users_count = options["users"]
        products_count = options["products"]
        orders_count = options["orders"]
        carts_count = options["carts"]
        reset_final_data = options["reset_final_data"]

        random.seed(2026)

        self.stdout.write("========================================")
        self.stdout.write("Final Dataset Seeding for Requirements 6-10")
        self.stdout.write("========================================")
        self.stdout.write(f"Users target: {users_count}")
        self.stdout.write(f"Products target: {products_count}")
        self.stdout.write(f"Orders target: {orders_count}")
        self.stdout.write(f"Carts target: {carts_count}")
        self.stdout.write("========================================")

        with transaction.atomic():
            if reset_final_data:
                self.stdout.write(self.style.WARNING("Deleting previous final-seed data only..."))

                final_users = User.objects.filter(username__startswith="final_user_")
                final_products = Product.objects.filter(name__startswith="Final Product ")

                OrderItem.objects.filter(order__user__in=final_users).delete()
                Order.objects.filter(user__in=final_users).delete()

                CartItem.objects.filter(cart__user__in=final_users).delete()
                Cart.objects.filter(user__in=final_users).delete()

                Stock.objects.filter(product__in=final_products).delete()
                final_products.delete()
                final_users.delete()

            self.stdout.write("Creating users...")
            users = []
            for i in range(1, users_count + 1):
                username = f"final_user_{i:03d}"
                user, _ = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@example.com",
                        "first_name": "Final",
                        "last_name": f"User {i:03d}",
                    }
                )
                users.append(user)

            self.stdout.write("Creating products and stock...")
            products = []
            categories = ["Laptop", "Phone", "Headset", "Keyboard", "Mouse", "Monitor", "Tablet", "Camera"]

            for i in range(1, products_count + 1):
                category = categories[(i - 1) % len(categories)]
                name = f"Final Product {i:03d} - {category}"
                price = Decimal(random.randint(10, 800)) + Decimal("0.99")

                product, _ = Product.objects.get_or_create(
                    name=name,
                    defaults={"price": price}
                )

                # If product existed, keep it but make sure it has a realistic price.
                if product.price != price:
                    product.price = price
                    product.save(update_fields=["price"])

                Stock.objects.update_or_create(
                    product=product,
                    defaults={"quantity": random.randint(200, 2000)}
                )

                products.append(product)

            self.stdout.write("Creating carts and cart items...")
            selected_cart_users = users[:min(carts_count, len(users))]

            for user in selected_cart_users:
                cart, _ = Cart.objects.get_or_create(user=user)

                # Recreate cart items for deterministic demo state.
                CartItem.objects.filter(cart=cart).delete()

                for product in random.sample(products, k=min(5, len(products))):
                    CartItem.objects.create(
                        cart=cart,
                        product=product,
                        quantity=random.randint(1, 4)
                    )

            self.stdout.write("Creating orders and order items...")

            # Make part of the catalog more popular to produce meaningful popular-products results.
            popular_pool = products[:max(10, products_count // 10)]
            normal_pool = products

            created_orders = 0
            created_order_items = 0
            completed_orders = 0
            pending_orders = 0

            for i in range(1, orders_count + 1):
                user = random.choice(users)

                # Most orders are completed because batch processing and popular products rely on completed sales.
                status = "completed" if random.random() < 0.80 else "pending"

                order = Order.objects.create(
                    user=user,
                    status=status,
                    total=Decimal("0.00")
                )

                items_count = random.randint(1, 4)
                order_total = Decimal("0.00")

                for _ in range(items_count):
                    if random.random() < 0.70:
                        product = random.choice(popular_pool)
                    else:
                        product = random.choice(normal_pool)

                    quantity = random.randint(1, 5)
                    price = product.price
                    order_total += price * quantity

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price=price
                    )
                    created_order_items += 1

                order.total = order_total
                order.save(update_fields=["total"])

                created_orders += 1
                if status == "completed":
                    completed_orders += 1
                else:
                    pending_orders += 1

                if i % 1000 == 0:
                    self.stdout.write(f"Created {i}/{orders_count} orders...")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Final dataset generated successfully."))
        self.stdout.write("========================================")
        self.stdout.write(f"Users available: {User.objects.count()}")
        self.stdout.write(f"Products available: {Product.objects.count()}")
        self.stdout.write(f"Stock rows available: {Stock.objects.count()}")
        self.stdout.write(f"Orders created in this run: {created_orders}")
        self.stdout.write(f"OrderItems created in this run: {created_order_items}")
        self.stdout.write(f"Completed orders in this run: {completed_orders}")
        self.stdout.write(f"Pending orders in this run: {pending_orders}")
        self.stdout.write(f"Carts available: {Cart.objects.count()}")
        self.stdout.write(f"CartItems available: {CartItem.objects.count()}")
        self.stdout.write("========================================")
        self.stdout.write("Run this next:")
        self.stdout.write("python manage.py db_summary")