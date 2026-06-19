import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


BASE_URL = "http://127.0.0.1:8000"


def post(path, payload):
    response = requests.post(f"{BASE_URL}{path}", json=payload, timeout=30)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    return response.status_code, data


def get(path):
    response = requests.get(f"{BASE_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def setup_acid_data(users=50, stock=20, wallet_balance=1000, product_price=50):
    status, data = post("/orders/acid/setup/", {
        "users": users,
        "stock": stock,
        "wallet_balance": wallet_balance,
        "product_price": product_price,
    })

    if status != 200:
        raise RuntimeError(f"Setup failed: {status} {data}")

    return data


def print_state(title):
    state = get("/orders/acid/state/")
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)
    print(f"Product stock:         {state['product']['stock_quantity']}")
    print(f"Single wallet balance: {state['single_user']['wallet_balance']}")
    print(f"Orders count:          {state['orders_count']}")
    print(f"OrderItems count:      {state['order_items_count']}")
    print(f"Wallet distribution:   {state['wallet_distribution']}")
    return state


def test_unsafe_failure():
    print("\n" + "═" * 70)
    print("SCENARIO 1: UNSAFE FAILURE — partial update problem")
    print("═" * 70)

    setup = setup_acid_data(users=0, stock=10, wallet_balance=1000, product_price=50)
    product_id = setup["product"]["id"]

    before = print_state("Before unsafe checkout failure")

    status, data = post("/orders/checkout-unsafe/", {
        "username": "acid_single_user",
        "product_id": product_id,
        "quantity": 1,
        "force_failure": True,
    })

    print("\nUnsafe response:")
    print("status:", status)
    print(data)

    after = print_state("After unsafe checkout failure")

    wallet_changed = after["single_user"]["wallet_balance"] != before["single_user"]["wallet_balance"]
    stock_changed = after["product"]["stock_quantity"] != before["product"]["stock_quantity"]
    order_not_created = after["orders_count"] == before["orders_count"]

    print("\nResult:")
    print(f"Wallet changed:     {wallet_changed}")
    print(f"Stock changed:      {stock_changed}")
    print(f"Order not created:  {order_not_created}")

    if wallet_changed and stock_changed and order_not_created:
        print("ISSUE DEMONSTRATED: partial update occurred without transaction.")
    else:
        print("WARNING: unsafe failure did not show the expected partial update.")


def test_safe_failure_rollback():
    print("\n" + "═" * 70)
    print("SCENARIO 2: SAFE FAILURE — rollback with transaction.atomic()")
    print("═" * 70)

    setup = setup_acid_data(users=0, stock=10, wallet_balance=1000, product_price=50)
    product_id = setup["product"]["id"]

    before = print_state("Before safe checkout failure")

    status, data = post("/orders/checkout-safe/", {
        "username": "acid_single_user",
        "product_id": product_id,
        "quantity": 1,
        "force_failure": True,
    })

    print("\nSafe failure response:")
    print("status:", status)
    print(data)

    after = print_state("After safe checkout failure")

    wallet_same = after["single_user"]["wallet_balance"] == before["single_user"]["wallet_balance"]
    stock_same = after["product"]["stock_quantity"] == before["product"]["stock_quantity"]
    order_not_created = after["orders_count"] == before["orders_count"]

    print("\nResult:")
    print(f"Wallet unchanged:   {wallet_same}")
    print(f"Stock unchanged:    {stock_same}")
    print(f"Order not created:  {order_not_created}")

    if wallet_same and stock_same and order_not_created:
        print("SOLUTION WORKING: rollback restored all changes.")
    else:
        print("WARNING: rollback result is not consistent.")


def test_safe_success():
    print("\n" + "═" * 70)
    print("SCENARIO 3: SAFE SUCCESS — all steps commit together")
    print("═" * 70)

    setup = setup_acid_data(users=0, stock=10, wallet_balance=1000, product_price=50)
    product_id = setup["product"]["id"]

    before = print_state("Before safe checkout success")

    status, data = post("/orders/checkout-safe/", {
        "username": "acid_single_user",
        "product_id": product_id,
        "quantity": 1,
        "force_failure": False,
    })

    print("\nSafe success response:")
    print("status:", status)
    print(data)

    after = print_state("After safe checkout success")

    wallet_deducted = after["single_user"]["wallet_balance"] == before["single_user"]["wallet_balance"] - 50
    stock_deducted = after["product"]["stock_quantity"] == before["product"]["stock_quantity"] - 1
    order_created = after["orders_count"] == before["orders_count"] + 1
    item_created = after["order_items_count"] == before["order_items_count"] + 1

    print("\nResult:")
    print(f"Wallet deducted:    {wallet_deducted}")
    print(f"Stock deducted:     {stock_deducted}")
    print(f"Order created:      {order_created}")
    print(f"OrderItem created:  {item_created}")

    if wallet_deducted and stock_deducted and order_created and item_created:
        print("SOLUTION WORKING: all checkout steps committed together.")
    else:
        print("WARNING: safe success result is not complete.")


def checkout_user(username, product_id):
    status, data = post("/orders/checkout-safe/", {
        "username": username,
        "product_id": product_id,
        "quantity": 1,
        "force_failure": False,
    })

    return {
        "username": username,
        "status": status,
        "data": data,
    }


def test_safe_concurrent_checkout():
    print("\n" + "═" * 70)
    print("SCENARIO 4: SAFE CONCURRENT CHECKOUT — 50 users, stock = 20")
    print("═" * 70)

    users_count = 50
    initial_stock = 20
    price = 50
    initial_balance = 1000

    setup = setup_acid_data(
        users=users_count,
        stock=initial_stock,
        wallet_balance=initial_balance,
        product_price=price,
    )

    product_id = setup["product"]["id"]

    before = print_state("Before concurrent checkout")

    usernames = [f"acid_user_{i:03d}" for i in range(1, users_count + 1)]

    results = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=users_count) as executor:
        futures = [
            executor.submit(checkout_user, username, product_id)
            for username in usernames
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    duration = time.time() - start

    success_count = sum(1 for r in results if r["status"] == 200)
    failed_count = len(results) - success_count
    stock_failures = sum(
        1 for r in results
        if r["status"] == 400 and "stock" in str(r["data"]).lower()
    )

    after = print_state("After concurrent checkout")

    expected_success = initial_stock
    expected_failed = users_count - initial_stock

    print("\nConcurrent result:")
    print(f"Total requests:       {users_count}")
    print(f"Success count:        {success_count}")
    print(f"Failed count:         {failed_count}")
    print(f"Stock failures:       {stock_failures}")
    print(f"Duration:             {duration:.2f}s")
    print(f"Expected success:     {expected_success}")
    print(f"Expected failed:      {expected_failed}")
    print(f"Final stock:          {after['product']['stock_quantity']}")
    print(f"Orders created:       {after['orders_count']}")
    print(f"OrderItems created:   {after['order_items_count']}")

    success_ok = success_count == expected_success
    failed_ok = failed_count == expected_failed
    stock_ok = after["product"]["stock_quantity"] == 0
    orders_ok = after["orders_count"] == expected_success
    items_ok = after["order_items_count"] == expected_success

    print("\nConsistency checks:")
    print(f"Success count correct:   {success_ok}")
    print(f"Failure count correct:   {failed_ok}")
    print(f"Final stock correct:     {stock_ok}")
    print(f"Orders count correct:    {orders_ok}")
    print(f"OrderItems count correct:{items_ok}")

    if success_ok and failed_ok and stock_ok and orders_ok and items_ok:
        print("SOLUTION WORKING: concurrent checkout stayed consistent.")
    else:
        print("WARNING: concurrent checkout is inconsistent.")


def main():
    print("\nRequirement #8: ACID / Transaction Integrity")
    print("Payment + stock update + order creation must commit or rollback together.")

    test_unsafe_failure()
    test_safe_failure_rollback()
    test_safe_success()
    test_safe_concurrent_checkout()

    print("\n" + "═" * 70)
    print("FINAL REQUIREMENT #8 SUMMARY")
    print("═" * 70)
    print("Unsafe failure: shows partial update without transaction.")
    print("Safe failure: transaction rollback keeps wallet, stock, and orders unchanged.")
    print("Safe success: wallet, stock, order, and order item commit together.")
    print("Concurrent safe checkout: only available stock succeeds; failed users are not partially charged.")
    print("═" * 70)


if __name__ == "__main__":
    main()