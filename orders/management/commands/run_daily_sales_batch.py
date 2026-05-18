import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from orders.models import Order, BatchJobRun, BatchChunkLog


def split_into_chunks(items, chunk_size):
    for start in range(0, len(items), chunk_size):
        end = min(start + chunk_size, len(items))
        yield start, end, items[start:end]


def process_chunk(job_run_id, chunk_number, start_index, end_index, order_ids):
    chunk_start = time.time()

    try:
        aggregate_result = Order.objects.filter(
            id__in=order_ids,
            status="completed"
        ).aggregate(
            revenue=Sum("total")
        )

        revenue = aggregate_result["revenue"] or Decimal("0.00")
        orders_count = len(order_ids)

        duration = time.time() - chunk_start

        BatchChunkLog.objects.create(
            job_run_id=job_run_id,
            chunk_number=chunk_number,
            start_index=start_index,
            end_index=end_index,
            orders_count=orders_count,
            revenue=revenue,
            status="completed",
            duration_seconds=round(duration, 4),
        )

        return {
            "chunk_number": chunk_number,
            "orders_count": orders_count,
            "revenue": revenue,
            "duration_seconds": round(duration, 4),
            "status": "completed",
        }

    except Exception as exc:
        duration = time.time() - chunk_start

        BatchChunkLog.objects.create(
            job_run_id=job_run_id,
            chunk_number=chunk_number,
            start_index=start_index,
            end_index=end_index,
            orders_count=0,
            revenue=Decimal("0.00"),
            status="failed",
            duration_seconds=round(duration, 4),
            error_message=str(exc),
        )

        return {
            "chunk_number": chunk_number,
            "orders_count": 0,
            "revenue": Decimal("0.00"),
            "duration_seconds": round(duration, 4),
            "status": "failed",
            "error": str(exc),
        }
class Command(BaseCommand):
     help = "Run daily sales batch processing using chunks and worker threads."

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
            help="Number of worker threads."
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

        if options["date"]:
            target_date = timezone.datetime.strptime(
                options["date"], "%Y-%m-%d"
            ).date()
        else:
            target_date = timezone.localdate()

        order_ids = list(
            Order.objects.filter(
                status="completed",
                created_at__date=target_date
            ).order_by("id").values_list("id", flat=True)
        )

        total_orders = len(order_ids)

        self.stdout.write("====================================")
        self.stdout.write("Daily Sales Batch Processing")
        self.stdout.write("====================================")
        self.stdout.write(f"Target date: {target_date}")
        self.stdout.write(f"Total completed orders: {total_orders}")
        self.stdout.write(f"Chunk size: {chunk_size}")
        self.stdout.write(f"Workers: {workers}")
        self.stdout.write("====================================")

        if total_orders == 0:
            self.stdout.write(self.style.WARNING(
                "No completed orders found for this date."
            ))
            return

        job_run = BatchJobRun.objects.create(
            job_name="daily_sales_batch",
            target_date=target_date,
            status="running",
            chunk_size=chunk_size,
            workers_count=workers,
            total_orders=total_orders,
        )

        chunks = list(split_into_chunks(order_ids, chunk_size))
        total_chunks = len(chunks)

        self.stdout.write(f"Total chunks: {total_chunks}")

        start_time = time.time()
        results = []

        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []

                for chunk_number, (start_index, end_index, chunk_order_ids) in enumerate(chunks, start=1):
                    futures.append(
                        executor.submit(
                            process_chunk,
                            job_run.id,
                            chunk_number,
                            start_index,
                            end_index,
                            chunk_order_ids,
                        )
                    )

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)

                    self.stdout.write(
                        f"Chunk {result['chunk_number']} finished | "
                        f"orders={result['orders_count']} | "
                        f"revenue={result['revenue']} | "
                        f"status={result['status']}"
                    )

            total_revenue = sum(
                result["revenue"]
                for result in results
                if result["status"] == "completed"
            )

            processed_orders = sum(
                result["orders_count"]
                for result in results
                if result["status"] == "completed"
            )

            duration = time.time() - start_time

            job_run.status = "completed"
            job_run.processed_orders = processed_orders
            job_run.total_revenue = total_revenue
            job_run.duration_seconds = round(duration, 4)
            job_run.finished_at = timezone.now()
            job_run.save()

            os.makedirs("reports", exist_ok=True)

            report_path = os.path.join(
                "reports",
                f"daily_sales_batch_run_{job_run.id}.csv"
            )

            with open(report_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "job_run_id",
                    "target_date",
                    "total_orders",
                    "processed_orders",
                    "total_revenue",
                    "chunk_size",
                    "workers",
                    "total_chunks",
                    "duration_seconds",
                ])
                writer.writerow([
                    job_run.id,
                    target_date,
                    total_orders,
                    processed_orders,
                    total_revenue,
                    chunk_size,
                    workers,
                    total_chunks,
                    round(duration, 4),
                ])

            self.stdout.write("====================================")
            self.stdout.write(self.style.SUCCESS("Batch job completed successfully."))
            self.stdout.write(f"Job run id: {job_run.id}")
            self.stdout.write(f"Processed orders: {processed_orders}")
            self.stdout.write(f"Total revenue: {total_revenue}")
            self.stdout.write(f"Duration: {duration:.4f}s")
            self.stdout.write(f"CSV report: {report_path}")
            self.stdout.write("====================================")

        except Exception as exc:
            duration = time.time() - start_time

            job_run.status = "failed"
            job_run.error_message = str(exc)
            job_run.duration_seconds = round(duration, 4)
            job_run.finished_at = timezone.now()
            job_run.save()

            self.stdout.write(self.style.ERROR(
                f"Batch job failed: {exc}"
            ))
    