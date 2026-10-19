"""Add editable customer profile details.

Revision ID: 0005_customer_profiles
Revises: 0004_loyalty_system
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_customer_profiles"
down_revision = "0004_loyalty_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("delivery_address", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("profile_image_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_image_url")
    op.drop_column("users", "delivery_address")
