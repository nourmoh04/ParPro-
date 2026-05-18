from decimal import Decimal
from random import randint, choice

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction

from products.models import Product
from orders.models import Order, OrderItem


class Command(BaseCommand):
    help = "Generate completed test orders for batch processing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1000,
            help="Number of completed orders to generate."
        )

    def handle(self, *args, **options):
        count = options["count"]

        user, _ = User.objects.get_or_create(username="batch_test_user")

        products = list(Product.objects.all())

        if not products:
            self.stdout.write("No products found. Creating sample products...")
            for i in range(1, 6):
                products.append(
                    Product.objects.create(
                        name=f"Batch Product {i}",
                        price=Decimal(str(10 * i))
                    )
                )

        self.stdout.write(f"Generating {count} completed orders...")

        start_time = timezone.now()

        with transaction.atomic():
            for i in range(count):
                product = choice(products)
                quantity = randint(1, 5)
                price = product.price
                total = price * quantity

                order = Order.objects.create(
                    user=user,
                    status="completed",
                    total=total
                )

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=price
                )

                if (i + 1) % 500 == 0:
                    self.stdout.write(f"Created {i + 1}/{count} orders...")

        duration = (timezone.now() - start_time).total_seconds()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully generated {count} completed orders in {duration:.2f}s."
        ))