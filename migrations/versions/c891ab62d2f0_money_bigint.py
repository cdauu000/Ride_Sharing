"""Widen integer-VND storage; SQLite already uses signed64-bit integer affinity.

Revision ID: c891ab62d2f0
Revises: b18db0479e61
"""

from alembic import op

revision = "c891ab62d2f0"
down_revision = "b18db0479e61"
branch_labels = None
depends_on = None

MONEY = {
    "scheduled_trips": ["seat_reference_vnd", "seat_price_vnd"],
    "bookings": [
        "pool_quote_price_vnd",
        "quoted_price_cap_vnd",
        "current_estimated_price_vnd",
        "final_price_vnd",
        "cancellation_fee_vnd",
    ],
    "fund_account": ["balance_vnd"],
    "fund_ledger": ["amount_signed_vnd", "balance_after_vnd"],
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in MONEY.items():
        for column in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE bigint")


def downgrade() -> None:
    # Preserve representable monetary values. A narrowing conversion must be an explicit migration.
    pass
