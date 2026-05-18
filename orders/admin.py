from django.contrib import admin
from .models import Order, OrderItem, Cart, CartItem, BatchJobRun, BatchChunkLog
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Cart)
admin.site.register(CartItem)
@admin.register(BatchJobRun)
class BatchJobRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job_name",
        "target_date",
        "status",
        "chunk_size",
        "workers_count",
        "total_orders",
        "processed_orders",
        "total_revenue",
        "duration_seconds",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "target_date", "job_name")
    search_fields = ("job_name",)


@admin.register(BatchChunkLog)
class BatchChunkLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job_run",
        "chunk_number",
        "start_index",
        "end_index",
        "orders_count",
        "revenue",
        "status",
        "duration_seconds",
        "created_at",
    )
    list_filter = ("status",)