from django.db import models
from django.contrib.auth.models import User
from products.models import Product

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2 ,default = 0.0)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

class BatchJobRun(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    job_name = models.CharField(max_length=100)
    target_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")

    chunk_size = models.PositiveIntegerField()
    workers_count = models.PositiveIntegerField(default=1)

    total_orders = models.PositiveIntegerField(default=0)
    processed_orders = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0)

    error_message = models.TextField(blank=True, default="")

    def str(self):
        return f"{self.job_name} - {self.target_date} - {self.status}"


class BatchChunkLog(models.Model):
    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    job_run = models.ForeignKey(
        BatchJobRun,
        on_delete=models.CASCADE,
        related_name="chunks"
    )

    chunk_number = models.PositiveIntegerField()
    start_index = models.PositiveIntegerField()
    end_index = models.PositiveIntegerField()

    orders_count = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    duration_seconds = models.FloatField(default=0)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def str(self):
        return f"Chunk {self.chunk_number} - {self.status}"