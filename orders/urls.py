from django.urls import path
from .import views

urlpatterns = [
    path("place-order/", views.place_order),
    path("place-order-unsafe/",views. place_order_unsafe),

    path("place-order-sync/", views.place_order_sync),
    path("place-order-async/", views.place_order_async),
    path("async-queue/status/", views.async_queue_status_view),

    path("process-payment-uncontrolled/", views.process_payment_uncontrolled),
    path("process-payment-controlled/", views.process_payment_controlled),
    path("payment-metrics/", views.payment_metrics_view),
    path("payment-metrics/reset/", views.reset_payment_metrics),
    
    path("run-sales-report-unsafe/",   views.run_sales_report_unsafe),
    path("run-sales-report-safe/",     views.run_sales_report_safe),
    path("distributed-lock-status/",   views.distributed_lock_status),

    path("acid/setup/", views.acid_test_setup),
    path("acid/state/", views.acid_state),
    path("checkout-unsafe/", views.checkout_unsafe),
    path("checkout-safe/", views.checkout_safe),
]
