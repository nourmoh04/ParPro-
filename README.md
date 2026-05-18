# ParPro E-Commerce Non-Functional Requirements Project

This project is a simplified Django-based E-Commerce backend used to demonstrate and test several non-functional requirements.

The goal of this project is not to build a full production-ready online shop with a user interface. Instead, the project focuses on backend behavior, performance, concurrency, resource usage, asynchronous processing, batch processing, and load distribution.

## Project Overview

The project contains basic E-Commerce entities:

- Products
- Stock
- Orders
- Order items
- Cart and cart items

These functional parts are used as a base for testing the required non-functional requirements.

Some external operations are simulated, such as:

- Payment processing
- Sending confirmation emails
- Generating invoices

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
test_race.py
```

Example commands:

```bash
python test_race.py unsafe
python test_race.py safe
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
monitor_resources.py
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
monitor_resources.py
```

Example monitor commands:

```bash
python monitor_resources.py uncontrolled_50
python monitor_resources.py controlled_50
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
test_async.py
```

Example command:

```bash
python test_async.py compare
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
test_load_balancer.py
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
python test_load_balancer.py round_robin
python test_load_balancer.py least_connections
python test_load_balancer.py ip_hash
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
```

Do not commit the real `.env` file to GitHub.

### 6. Apply migrations

```bash
python manage.py migrate
```

### 7. Run the development server

```bash
python manage.py runserver
```

Default server:

```text
http://127.0.0.1:8000/
```

---

## Test Files

| Requirement | Test / Tool | File |
|---|---|---|
| Race Condition | Python threading test | `test_race.py` |
| Resource Management | JMeter + resource monitor | `tests/jmeter/resource_management_test.jmx`, `monitor_resources.py` |
| Async Queue | Python threading test | `test_async.py` |
| Batch Processing | Django management commands | `seed_batch_orders.py`, `compare_daily_sales_processing.py`, `run_daily_sales_batch.py` |
| Load Distribution | Python threading test | `test_load_balancer.py` |

---

## Useful Test Commands

### Requirement 1

```bash
python test_race.py unsafe
python test_race.py safe
```

### Requirement 2

Run the Django server first:

```bash
python manage.py runserver
```

Then run the JMeter test plan:

```text
tests/jmeter/resource_management_test.jmx
```

Resource monitor examples:

```bash
python monitor_resources.py uncontrolled_50
python monitor_resources.py controlled_50
```

### Requirement 3

```bash
python test_async.py compare
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
python test_load_balancer.py round_robin
python test_load_balancer.py least_connections
python test_load_balancer.py ip_hash
```

---

## Notes

- This project is backend-focused.
- Some operations are simulated to focus on non-functional behavior.
- The project uses PostgreSQL.
- The `.env` file should not be uploaded to GitHub.
- Generated reports and runtime outputs should not be committed unless required for documentation.
- JMeter is used for the resource management test.
- The internal async queue can be replaced by Redis/Celery or RabbitMQ in a production environment.
- The Django-based load balancer is used for educational purposes. In production, systems usually use Nginx, HAProxy, or cloud load balancers.

---

## Current Status

Implemented requirements:

```text
Requirement 1: Completed
Requirement 2: Completed
Requirement 3: Completed
Requirement 4: Completed
Requirement 5: Completed
```
