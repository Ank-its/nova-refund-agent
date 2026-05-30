"""Idempotent database seed — runs on every boot, no-ops if already seeded.

Populates 15 accounts engineered to exercise every branch of the rule matrix
and the evaluation scenarios. All accounts share the password ``demo1234``.

  CUSTOMERS
    alice    gold      Golden path: recent, eligible auto-approve
    bob      standard  High-value item (>$500) -> pending review
    carol    silver    Final-sale (clearance) -> hard block
    dave     standard  Velocity abuse: 3 approved refunds / 30d
    erin     platinum  Window breach (45d) + damage-escalation (50d)
    frank    standard  Ambiguous loop: only "this month" orders
    grace    gold      Ambiguous loop: only historical (>month)
    heidi    standard  Ambiguous loop: "this week" orders present
    ivan     silver    Single order -> item-name resolution (Scenario 1)
    judy     standard  Idempotency: order already refunded
    mallory  standard  Adversarial target (high-value laptop)
    oscar    gold      Clean item + final-sale item side by side
  ADMIN (no customer profile -> chat disabled, telemetry only)
    admin, ops_admin
  SUPER-USER / HYBRID (customer profile + admin rights)
    superuser
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.db.schema import Customer, Order, Refund, User, utcnow

PASSWORD = "demo1234"


def _days_ago(n: int):
    return utcnow() - timedelta(days=n)


# order:  (ref, item, amount, days_ago, is_final_sale)
# refund: (order_ref, status, amount, days_ago, reason)
ACCOUNTS: list[dict] = [
    {"username": "alice", "role": "customer", "tier": "gold",
     "full_name": "Alice Nguyen", "email": "alice@example.com",
     "orders": [("ORD_1001", "Wireless Headphones", 89.99, 3, False),
                ("ORD_1002", "USB-C Cable", 12.50, 5, False)], "refunds": []},
    {"username": "bob", "role": "customer", "tier": "standard",
     "full_name": "Bob Martinez", "email": "bob@example.com",
     "orders": [("ORD_1003", "4K OLED TV", 1299.00, 4, False)], "refunds": []},
    {"username": "carol", "role": "customer", "tier": "silver",
     "full_name": "Carol Davis", "email": "carol@example.com",
     "orders": [("ORD_1004", "Clearance Winter Jacket", 59.00, 4, True)], "refunds": []},
    {"username": "dave", "role": "customer", "tier": "standard",
     "full_name": "Dave Wilson", "email": "dave@example.com",
     "orders": [("ORD_1005", "Bluetooth Speaker", 45.00, 2, False),
                ("ORD_1006", "Phone Charger", 22.00, 25, False),
                ("ORD_1007", "Laptop Sleeve", 30.00, 18, False),
                ("ORD_1008", "Webcam", 55.00, 10, False)],
     "refunds": [("ORD_1006", "approved", 22.00, 24, "changed mind"),
                 ("ORD_1007", "approved", 30.00, 17, "no longer needed"),
                 ("ORD_1008", "approved", 55.00, 9, "found cheaper")]},
    {"username": "erin", "role": "customer", "tier": "platinum",
     "full_name": "Erin Thompson", "email": "erin@example.com",
     "orders": [("ORD_1009", "Office Chair", 210.00, 45, False),
                ("ORD_1010", "Standing Desk", 330.00, 50, False)], "refunds": []},
    {"username": "frank", "role": "customer", "tier": "standard",
     "full_name": "Frank Lee", "email": "frank@example.com",
     "orders": [("ORD_1011", "Notebook Planner", 8.00, 12, False)], "refunds": []},
    {"username": "grace", "role": "customer", "tier": "gold",
     "full_name": "Grace Patel", "email": "grace@example.com",
     "orders": [("ORD_1012", "Desk Lamp", 25.00, 120, False)], "refunds": []},
    {"username": "heidi", "role": "customer", "tier": "standard",
     "full_name": "Heidi Brown", "email": "heidi@example.com",
     "orders": [("ORD_1013", "Wireless Mouse", 19.99, 2, False),
                ("ORD_1014", "Mechanical Keyboard", 39.99, 4, False)], "refunds": []},
    {"username": "ivan", "role": "customer", "tier": "silver",
     "full_name": "Ivan Petrov", "email": "ivan@example.com",
     "orders": [("ORD_1015", "Water Bottle", 15.00, 6, False)], "refunds": []},
    {"username": "judy", "role": "customer", "tier": "standard",
     "full_name": "Judy Garcia", "email": "judy@example.com",
     "orders": [("ORD_1016", "Phone Case", 18.00, 5, False)],
     "refunds": [("ORD_1016", "approved", 18.00, 3, "defective")]},
    {"username": "mallory", "role": "customer", "tier": "standard",
     "full_name": "Mallory Singh", "email": "mallory@example.com",
     "orders": [("ORD_9901", "Premium Laptop", 1500.00, 3, False)], "refunds": []},
    {"username": "oscar", "role": "customer", "tier": "gold",
     "full_name": "Oscar Reyes", "email": "oscar@example.com",
     "orders": [("ORD_1018", "Ceramic Vase", 40.00, 10, False),
                ("ORD_1019", "Final Sale Mug", 9.00, 6, True)], "refunds": []},
    {"username": "admin", "role": "admin", "tier": None,
     "full_name": "Platform Admin", "email": "admin@example.com",
     "orders": [], "refunds": []},
    {"username": "ops_admin", "role": "admin", "tier": None,
     "full_name": "Operations Admin", "email": "ops@example.com",
     "orders": [], "refunds": []},
    {"username": "superuser", "role": "superuser", "tier": "platinum",
     "full_name": "Sam Hybrid", "email": "superuser@example.com",
     "orders": [("ORD_1017", "Monitor Stand", 35.00, 3, False)], "refunds": []},
]


async def seed() -> None:
    async with SessionLocal() as session:
        if await session.scalar(select(User).limit(1)) is not None:
            print("[seed] Database already seeded — skipping.")
            return

        for acc in ACCOUNTS:
            user = User(
                username=acc["username"],
                password_hash=hash_password(PASSWORD),
                role=acc["role"],
            )
            session.add(user)
            await session.flush()

            customer = None
            if acc["tier"] is not None:
                customer = Customer(
                    user_id=user.id,
                    full_name=acc["full_name"],
                    email=acc["email"],
                    loyalty_tier=acc["tier"],
                )
                session.add(customer)
                await session.flush()

            ref_to_order: dict[str, Order] = {}
            for ref, item, amount, days_ago, final_sale in acc["orders"]:
                assert customer is not None
                order = Order(
                    order_ref=ref,
                    customer_id=customer.id,
                    item_name=item,
                    amount=Decimal(str(amount)),
                    purchase_date=_days_ago(days_ago),
                    is_final_sale=final_sale,
                )
                session.add(order)
                await session.flush()
                ref_to_order[ref] = order

            for ref, status, amount, days_ago, reason in acc["refunds"]:
                assert customer is not None
                refund = Refund(
                    order_id=ref_to_order[ref].id,
                    customer_id=customer.id,
                    status=status,
                    reason=reason,
                    amount=Decimal(str(amount)),
                    decision_detail="seeded historical refund",
                )
                refund.created_at = _days_ago(days_ago)
                session.add(refund)

        await session.commit()
        print(f"[seed] Seeded {len(ACCOUNTS)} accounts (password: {PASSWORD}).")
