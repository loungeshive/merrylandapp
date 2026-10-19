"""Add managed menu prices and customer ratings.

Revision ID: 0003_managed_menu
Revises: 0002_google_auth
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0003_managed_menu"
down_revision = "0002_google_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_items", sa.Column("marked_price_minor", sa.Integer(), nullable=True))

    connection = op.get_bind()
    category_ids = {
        row["name"]: row["id"]
        for row in connection.execute(sa.text("SELECT id, name FROM categories")).mappings()
    }
    if "Main meals" in category_ids:
        if "Food" in category_ids:
            connection.execute(
                sa.text("UPDATE menu_items SET category_id = :food_id WHERE category_id = :meals_id"),
                {"food_id": category_ids["Food"], "meals_id": category_ids["Main meals"]},
            )
            connection.execute(
                sa.text("DELETE FROM categories WHERE id = :meals_id"),
                {"meals_id": category_ids["Main meals"]},
            )
        else:
            connection.execute(
                sa.text("UPDATE categories SET name = 'Food', sort_order = 1 WHERE id = :meals_id"),
                {"meals_id": category_ids["Main meals"]},
            )

    category_ids = {
        row["name"]: row["id"]
        for row in connection.execute(sa.text("SELECT id, name FROM categories")).mappings()
    }
    for order, name in enumerate(("Food", "Drinks", "Bites"), start=1):
        if name not in category_ids:
            connection.execute(
                sa.text(
                    "INSERT INTO categories (id, name, sort_order, active) "
                    "VALUES (:id, :name, :sort_order, :active)"
                ),
                {"id": str(uuid4()), "name": name, "sort_order": order, "active": True},
            )
        else:
            connection.execute(
                sa.text("UPDATE categories SET sort_order = :sort_order, active = 1 WHERE name = :name"),
                {"name": name, "sort_order": order},
            )

    connection.execute(
        sa.text(
            "UPDATE menu_items SET available = FALSE "
            "WHERE name IN ('Merryland Grilled Chicken', 'Beef Pilau', 'Fresh Passion Juice')"
        )
    )

    op.create_table(
        "menu_ratings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "menu_item_id",
            sa.String(length=36),
            sa.ForeignKey("menu_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("menu_item_id", "customer_id", name="uq_menu_rating_customer_item"),
    )
    op.create_index("ix_menu_ratings_menu_item_id", "menu_ratings", ["menu_item_id"])
    op.create_index("ix_menu_ratings_customer_id", "menu_ratings", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_menu_ratings_customer_id", table_name="menu_ratings")
    op.drop_index("ix_menu_ratings_menu_item_id", table_name="menu_ratings")
    op.drop_table("menu_ratings")
    op.drop_column("menu_items", "marked_price_minor")
