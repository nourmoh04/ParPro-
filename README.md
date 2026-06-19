# ParPro E-Commerce Non-Functional Requirements Project

This project is a simplified Django-based E-Commerce backend used to demonstrate and test several non-functional requirements.

The goal of this project is not to build a full production-ready online shop with a user interface. Instead, the project focuses on backend behavior, performance, concurrency, resource usage, asynchronous processing, batch processing, caching, distributed locking, transaction integrity, stress testing, and benchmarking.

## Project Overview

The project contains basic E-Commerce entities:

- Products
- Stock
- Orders
- Order items
- Cart and cart items
- User wallets

These functional parts are used as a base for testing the required non-functional requirements.

Some external operations are simulated, such as:

- Payment processing
- Sending confirmation emails
- Generating invoices
- Sales report generation

These operations are simulated because the main goal is to test non-functional behavior, not to integrate real payment gateways, real email services, or real invoice providers.

## Implemented Requirements

### Requirement 1: Race Condition Handling

This requirement demonstrates what can happen when multiple users try to buy the same product at the same time.

Implemented endpoints:

- `/orders/place-order-unsafe/`
- `/orders/place-order/`

The unsafe endpoint does not use row-level locking and can lead to inconsistent stock updates.

The safe endpoint uses:

- `transaction.atomic()`
- `select_for_update()`

This locks the stock row during the order process and prevents inconsistent updates.

Test file:

```text
tests/test_race.py
```

Example commands:

```bash
python -m tests.test_race unsafe
python -m tests.test_race safe
```

Expected result:

- The unsafe version demonstrates the race condition problem.
- The safe version keeps the final stock consistent.

---

### Requirement 2: Resource Management and Capacity Control

This requirement simulates a heavy payment processing operation.

Implemented endpoints:

- `/orders/process-payment-uncontrolled/`
- `/orders/process-payment-controlled/`

The uncontrolled endpoint executes every payment request directly.

The controlled endpoint uses a `ThreadPoolExecutor` with a limited number of workers. This limits the number of heavy payment operations running at the same time.

Related files:

```text
orders/views.py
orders/urls.py
tests/monitor_resources.py
tests/jmeter/resource_management_test.jmx
```

Useful endpoints:

```text
/orders/payment-metrics/
/orders/payment-metrics/reset/
```

JMeter test plan:

```text
tests/jmeter/resource_management_test.jmx
```

Resource monitor:

```text
tests/monitor_resources.py
```

Example monitor commands:

```bash
python -m tests.monitor_resources uncontrolled
python -m tests.monitor_resources controlled
```

Expected result:

- Uncontrolled processing allows many payment tasks to run at the same time.
- Controlled processing limits active payment tasks to the configured worker count.

---

### Requirement 3: Asynchronous Queue

This requirement shows how slow secondary tasks can be moved outside the main request-response flow.

The synchronous endpoint waits for:

- Sending confirmation email
- Generating invoice

The asynchronous endpoint creates the order quickly and adds the email and invoice tasks to an internal background queue.

Implemented endpoints:

```text
/orders/place-order-sync/
/orders/place-order-async/
/orders/async-queue/status/
```

The asynchronous queue is implemented using Python `queue.Queue` and a background worker thread.

Related files:

```text
orders/async_queue.py
tests/test_async.py
```

Example command:

```bash
python -m tests.test_async compare
```

Expected result:

- The synchronous version has a higher response time because the user waits for email and invoice processing.
- The asynchronous version returns quickly while the email and invoice tasks continue in the background.

Note:

This project uses an internal queue implementation for educational purposes. In a production environment, this can be replaced with Redis/Celery, RabbitMQ, Kafka, or another external queue system.

---

### Requirement 4: Batch Processing

This requirement implements a daily sales batch processing job.

The system processes completed orders in chunks instead of processing everything as one large operation.

Implemented features:

- Generate test orders
- Process daily sales in chunks
- Store batch job runs
- Store chunk logs
- Generate CSV report
- Compare naive sequential processing with chunk-based batch processing

Related files:

```text
orders/management/commands/seed_batch_orders.py
orders/management/commands/run_daily_sales_batch.py
orders/management/commands/compare_daily_sales_processing.py
orders/migrations/0003_batchjobrun_batchchunklog.py
```

Example commands:

```bash
python manage.py seed_batch_orders --count 1000
python manage.py compare_daily_sales_processing --chunk-size 100 --workers 4 --simulate-ms 2
python manage.py run_daily_sales_batch --chunk-size 100 --workers 4
```

Generated reports are stored in:

```text
reports/
```

The `reports/` folder is ignored by Git because it contains generated local results.

Expected result:

- Orders are processed in chunks.
- Batch results are stored.
- Chunk logs are stored.
- A CSV report is generated.

---

### Requirement 5: Load Distribution

This requirement demonstrates load distribution across multiple application instances.

The project includes an application-level load balancer that routes requests to three backend Django instances.

Backend instances:

```text
server_1 -> http://127.0.0.1:8001
server_2 -> http://127.0.0.1:8002
server_3 -> http://127.0.0.1:8003
```

The load balancer runs on:

```text
http://127.0.0.1:8000
```

Related files:

```text
load_balancer/
tests/test_load_balancer.py
```

Implemented strategies:

- Round Robin
- Least Connections
- IP Hash

Useful endpoints:

```text
/load-balancer/route/
/load-balancer/stats/
/load-balancer/reset/
```

To test load distribution, run four Django servers in four separate terminals:

```bash
python manage.py runserver 8000
python manage.py runserver 8001
python manage.py runserver 8002
python manage.py runserver 8003
```

Then run:

```bash
python -m tests.test_load_balancer round_robin
python -m tests.test_load_balancer least_connections
python -m tests.test_load_balancer ip_hash
```

Expected Round Robin result:

```text
server_1: 10 requests
server_2: 10 requests
server_3: 10 requests
```

This proves that requests are distributed across multiple application instances.

Note:

The IP Hash strategy usually sends all local requests to the same server because all requests come from the same local IP address. This is expected behavior and is not considered a failure.

---

### Requirement 6: Distributed Caching

This requirement implements Redis-based caching for product-related endpoints.

Implemented endpoints:

```text
/products/list-uncached/
/products/list-cached/
/products/<product_id>/detail-uncached/
/products/<product_id>/detail-cached/
/products/popular-uncached/
/products/popular-cached/
/products/cache-metrics/
/products/cache-metrics/reset/
/products/cache-clear/
```

The cached endpoints use Redis to reduce repeated database reads for frequently requested product data.

Related files:

```text
products/views.py
products/urls.py
tests/test_cache.py
```

Example command:

```bash
python -m tests.test_cache
```

Expected result:

- The first cached request is a cache miss.
- The second cached request is a cache hit.
- Cached responses are faster than uncached responses.
- Database reads do not increase on cache hits.

---

### Requirement 7: Distributed Lock

This requirement implements a Redis distributed lock to prevent the same heavy background job from running multiple times at the same time.

Implemented endpoints:

```text
/orders/run-sales-report-unsafe/
/orders/run-sales-report-safe/
/orders/distributed-lock-status/
```

The unsafe endpoint allows multiple concurrent sales report jobs to run at once.

The safe endpoint uses Redis `SET NX EX` to allow only one job to run while the other requests are blocked by the distributed lock.

Related files:

```text
orders/distributed_lock.py
orders/views.py
orders/urls.py
tests/test_distributed_lock.py
```

Example commands:

```bash
python -m tests.test_distributed_lock 10
python -m tests.test_distributed_lock 50
```

Expected result:

- Before using the Redis lock, all concurrent jobs can start.
- After using the Redis lock, only one job starts and the remaining requests are blocked.
- This requirement uses Redis locking, while Requirement 1 uses database row locking.

---

### Requirement 8: ACID Transaction Integrity

This requirement demonstrates that payment, stock update, order creation, and order item creation must commit or rollback together.

Implemented endpoints:

```text
/orders/acid/setup/
/orders/acid/state/
/orders/checkout-unsafe/
/orders/checkout-safe/
```

The unsafe checkout can leave partial updates if a failure happens after wallet and stock changes.

The safe checkout uses:

```text
transaction.atomic()
select_for_update()
```

This ensures that wallet balance, stock quantity, order creation, and order item creation are handled as one atomic transaction.

Related files:

```text
orders/models.py
orders/views.py
orders/urls.py
orders/migrations/0004_userwallet.py
tests/test_acid.py
```

Example command:

```bash
python -m tests.test_acid
```

Expected result:

- Unsafe failure demonstrates a partial update problem.
- Safe failure rolls back all changes.
- Safe success commits wallet, stock, order, and order item together.
- Concurrent safe checkout remains consistent.

---

### Requirement 9: Stress Testing

This requirement tests the system under 100 concurrent users.

Each simulated user performs a realistic E-Commerce journey:

```text
1. View cached product list
2. View cached product detail
3. View cached popular products
4. Perform safe checkout
```

The test uses existing final seed data and creates or tops up wallets only when needed because the wallet model was introduced later.

Related files:

```text
tests/test_stress.py
```

Example command:

```bash
python -m tests.test_stress
```

Expected result:

- 100 users are simulated concurrently.
- Around 400 requests are executed.
- The system should handle the requests without server failure.
- The test reports response time, success rate, throughput, and slowest endpoints.

---

### Requirement 10: Benchmarking and Bottleneck Analysis

This requirement uses benchmarking and structured request logs to identify and improve a performance bottleneck.

The stress test showed that returning the full product catalog can become expensive under load. The improvement adds a cached paginated product list endpoint.

Implemented endpoint:

```text
/products/list-paginated-cached/?page=1&page_size=100
```

The benchmark compares:

```text
Before: /products/list-cached/
After:  /products/list-paginated-cached/?page=1&page_size=100
```

Related files:

```text
ParPro/request_logging.py
products/views.py
products/urls.py
tests/test_benchmark.py
```

Example command:

```bash
python -m tests.test_benchmark
```

Expected result:

- The paginated cached endpoint returns fewer products per response.
- Payload size is reduced.
- Average response time and P95 response time improve.
- Throughput increases.

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/nourmoh04/ParPro-.git
cd ParPro-
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the PostgreSQL database

Create a PostgreSQL database named:

```text
parpro_db
```

### 5. Create a `.env` file

Create a `.env` file in the root directory of the project.

Example:

```env
SECRET_KEY=your-secret-key
DEBUG=True

DB_NAME=parpro_db
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/1
CACHE_TTL_SECONDS=60
```

Do not commit the real `.env` file to GitHub.

### 6. Start Redis or Memurai

Requirements 6 and 7 require Redis or a Redis-compatible server such as Memurai.

Example Memurai check on Windows:

```powershell
& "C:\Program Files\Memurai\memurai-cli.exe" ping
```

Expected result:

```text
PONG
```

### 7. Apply migrations

```bash
python manage.py migrate
```

### 8. Seed or prepare data

If the database is empty, create enough products, users, stock rows, and orders for the tests.

Useful commands:

```bash
python manage.py seed_batch_orders --count 1000
python manage.py seed_final_data --users 1500 --products 3000 --orders 6000 --carts 1000 --reset-final-data
```

### 9. Run the development server

```bash
python manage.py runserver 8000
```

Default server:

```text
http://127.0.0.1:8000/
```

---

## Test Files

| Requirement | Test / Tool | File |
|---|---|---|
| Requirement 1: Race Condition | Python threading test | `tests/test_race.py` |
| Requirement 2: Resource Management | JMeter + resource monitor | `tests/jmeter/resource_management_test.jmx`, `tests/monitor_resources.py` |
| Requirement 3: Async Queue | Python comparison test | `tests/test_async.py` |
| Requirement 4: Batch Processing | Django management commands | `orders/management/commands/` |
| Requirement 5: Load Distribution | Python threading test | `tests/test_load_balancer.py` |
| Requirement 6: Distributed Caching | Python cache test | `tests/test_cache.py` |
| Requirement 7: Distributed Lock | Python concurrency test | `tests/test_distributed_lock.py` |
| Requirement 8: ACID Transaction Integrity | Python transaction test | `tests/test_acid.py` |
| Requirement 9: Stress Testing | Python stress test | `tests/test_stress.py` |
| Requirement 10: Benchmarking | Python benchmark test | `tests/test_benchmark.py` |

---

## Useful Test Commands

Most Python test scripts are stored inside the `tests/` folder and should be executed as Python modules from the project root.

Run the Django server first for API-based tests:

```bash
python manage.py runserver 8000
```

### Requirement 1

```bash
python -m tests.test_race unsafe
python -m tests.test_race safe
```

### Requirement 2

Run the Django server first:

```bash
python manage.py runserver 8000
```

Reset payment metrics:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/orders/payment-metrics/reset/
```

Run the JMeter test plan:

```text
tests/jmeter/resource_management_test.jmx
```

Resource monitor examples:

```bash
python -m tests.monitor_resources uncontrolled
python -m tests.monitor_resources controlled
```

Metrics endpoint:

```text
/orders/payment-metrics/
```

### Requirement 3

```bash
python -m tests.test_async compare
```

### Requirement 4

```bash
python manage.py seed_batch_orders --count 1000
python manage.py compare_daily_sales_processing --chunk-size 100 --workers 4 --simulate-ms 2
python manage.py run_daily_sales_batch --chunk-size 100 --workers 4
```

### Requirement 5

Run four servers:

```bash
python manage.py runserver 8000
python manage.py runserver 8001
python manage.py runserver 8002
python manage.py runserver 8003
```

Then run:

```bash
python -m tests.test_load_balancer round_robin
python -m tests.test_load_balancer least_connections
python -m tests.test_load_balancer ip_hash
```

### Requirement 6

```bash
python -m tests.test_cache
```

### Requirement 7

```bash
python -m tests.test_distributed_lock 10
python -m tests.test_distributed_lock 50
```

### Requirement 8

```bash
python -m tests.test_acid
```

### Requirement 9

```bash
python -m tests.test_stress
```

### Requirement 10

```bash
python -m tests.test_benchmark
```

---

## Notes

- This project is backend-focused.
- Some operations are simulated to focus on non-functional behavior.
- The project uses PostgreSQL.
- Redis or Memurai is used for distributed caching and distributed locking.
- The `.env` file should not be uploaded to GitHub.
- Generated reports, logs, benchmark outputs, and runtime outputs should not be committed unless required for documentation.
- JMeter is used for the resource management test.
- The internal async queue can be replaced by Redis/Celery or RabbitMQ in a production environment.
- The Django-based load balancer is used for educational purposes. In production, systems usually use Nginx, HAProxy, or cloud load balancers.
- Test files are organized under the `tests/` folder. They should be executed from the project root using `python -m tests.<module_name>`.

---

## Current Status

Implemented requirements:

```text
Requirement 1: Completed
Requirement 2: Completed
Requirement 3: Completed
Requirement 4: Completed
Requirement 5: Completed
Requirement 6: Completed
Requirement 7: Completed
Requirement 8: Completed
Requirement 9: Completed
Requirement 10: Completed
```
