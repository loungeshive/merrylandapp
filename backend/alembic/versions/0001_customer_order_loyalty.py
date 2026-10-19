"""Create initial customer ordering and loyalty schema.

Revision ID: 0001_customer_order_loyalty
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_customer_order_loyalty"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])
    op.create_table(
        "categories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("category_id", sa.String(length=36), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("prep_minutes", sa.Integer(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("points_eligible", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_menu_items_category_id", "menu_items", ["category_id"])
    op.create_index("ix_menu_items_available", "menu_items", ["available"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_number", sa.String(length=20), nullable=False, unique=True),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("table_number", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), sa.ForeignKey("menu_items.id"), nullable=False),
        sa.Column("item_name", sa.String(length=120), nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("points_eligible", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=100), nullable=True, unique=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_table(
        "loyalty_transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_loyalty_idempotency_key"),
    )
    op.create_index("ix_loyalty_transactions_customer_id", "loyalty_transactions", ["customer_id"])
    op.create_index("ix_loyalty_transactions_order_id", "loyalty_transactions", ["order_id"])
    op.create_table(
        "rewards",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("points_cost", sa.Integer(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rewards")
    op.drop_index("ix_loyalty_transactions_order_id", table_name="loyalty_transactions")
    op.drop_index("ix_loyalty_transactions_customer_id", table_name="loyalty_transactions")
    op.drop_table("loyalty_transactions")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_menu_items_available", table_name="menu_items")
    op.drop_index("ix_menu_items_category_id", table_name="menu_items")
    op.drop_table("menu_items")
    op.drop_table("categories")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
