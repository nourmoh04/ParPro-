import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order


def split_into_chunks(items, chunk_size):
    for start in range(0, len(items), chunk_size):
        end = min(start + chunk_size, len(items))
        yield start, end, items[start:end]


def simulate_order_report_work(milliseconds):
    """
    Simulates small per-order processing work, such as preparing
    report rows, transforming data, or exporting sales information.
    """
    if milliseconds > 0:
        time.sleep(milliseconds / 1000)


def process_chunk_for_comparison(chunk_number, chunk_orders, simulate_ms):
    chunk_start = time.time()

    revenue = Decimal("0.00")

    for order in chunk_orders:
        simulate_order_report_work(simulate_ms)
        revenue += order.total

    duration = time.time() - chunk_start

    return {
        "chunk_number": chunk_number,
        "orders_count": len(chunk_orders),
        "revenue": revenue,
        "duration_seconds": duration,
    }
class Command(BaseCommand):
    help = "Compare sequential naive processing with chunk-based parallel batch processing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=100,
            help="Number of orders per chunk."
        )

        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Number of worker threads for batch processing."
        )

        parser.add_argument(
            "--simulate-ms",
            type=float,
            default=2.0,
            help="Simulated processing time per order in milliseconds."
        )

        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target date in YYYY-MM-DD format. Default: today."
        )

    def handle(self, *args, **options):
        chunk_size = options["chunk_size"]
        workers = options["workers"]
        simulate_ms = options["simulate_ms"]

        if options["date"]:
            target_date = timezone.datetime.strptime(
                options["date"], "%Y-%m-%d"
            ).date()
        else:
            target_date = timezone.localdate()

        orders = list(
            Order.objects.filter(
                status="completed",
                created_at__date=target_date
            ).order_by("id")
        )

        total_orders = len(orders)

        self.stdout.write("====================================")
        self.stdout.write("Daily Sales Processing Comparison")
        self.stdout.write("====================================")
        self.stdout.write(f"Target date: {target_date}")
        self.stdout.write(f"Total completed orders: {total_orders}")
        self.stdout.write(f"Chunk size: {chunk_size}")
        self.stdout.write(f"Workers: {workers}")
        self.stdout.write(f"Simulated work per order: {simulate_ms} ms")
        self.stdout.write("====================================")

        if total_orders == 0:
            self.stdout.write(self.style.WARNING(
                "No completed orders found for this date."
            ))
            return

        naive_start = time.time()

        naive_revenue = Decimal("0.00")

        for order in orders:
            simulate_order_report_work(simulate_ms)
            naive_revenue += order.total

        naive_duration = time.time() - naive_start

        self.stdout.write("")
        self.stdout.write("NAIVE SEQUENTIAL PROCESSING")
        self.stdout.write("------------------------------------")
        self.stdout.write("Method: process all orders one by one without chunks or workers")
        self.stdout.write(f"Orders processed: {total_orders}")
        self.stdout.write(f"Total revenue: {naive_revenue}")
        self.stdout.write(f"Duration: {naive_duration:.4f}s")

        batch_start = time.time()

        chunks = list(split_into_chunks(orders, chunk_size))
        batch_results = []

        self.stdout.write("")
        self.stdout.write("CHUNK-BASED BATCH PROCESSING")
        self.stdout.write("------------------------------------")
        self.stdout.write(
            f"Method: process {len(chunks)} chunks using {workers} workers"
        )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []

            for chunk_number, (start_index, end_index, chunk_orders) in enumerate(chunks, start=1):
                futures.append(
                    executor.submit(
                        process_chunk_for_comparison,
                        chunk_number,
                        chunk_orders,
                        simulate_ms,
                    )
                )

            for future in as_completed(futures):
                result = future.result()
                batch_results.append(result)

                self.stdout.write(
                    f"Chunk {result['chunk_number']:02d}: "
                    f"orders={result['orders_count']} | "
                    f"revenue={result['revenue']} | "
                    f"duration={result['duration_seconds']:.4f}s"
                )

        batch_duration = time.time() - batch_start

        batch_revenue = sum(
            result["revenue"]
            for result in batch_results
        )

        batch_processed_orders = sum(
            result["orders_count"]
            for result in batch_results
        )

        speedup = naive_duration / batch_duration if batch_duration > 0 else 0

        self.stdout.write("")
        self.stdout.write("COMPARISON RESULT")
        self.stdout.write("====================================")
        self.stdout.write(f"Naive revenue: {naive_revenue}")
        self.stdout.write(f"Batch revenue: {batch_revenue}")
        self.stdout.write(f"Revenue consistent: {naive_revenue == batch_revenue}")
        self.stdout.write(f"Naive duration: {naive_duration:.4f}s")
        self.stdout.write(f"Batch duration: {batch_duration:.4f}s")
        self.stdout.write(f"Speedup: {speedup:.2f}x")
        self.stdout.write(f"Chunks processed: {len(chunks)}")
        self.stdout.write(f"Orders processed by batch: {batch_processed_orders}")

        if naive_revenue == batch_revenue and batch_processed_orders == total_orders:
            self.stdout.write(self.style.SUCCESS(
                "Comparison successful: batch processing produced consistent results."
            ))
        else:
            self.stdout.write(self.style.ERROR(
                "Comparison failed: results are not consistent."
            ))

        self.stdout.write("====================================")