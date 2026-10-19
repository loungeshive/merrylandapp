"""Allow Google-authenticated users without a password or phone.

Revision ID: 0002_google_auth
Revises: 0001_customer_order_loyalty
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_google_auth"
down_revision = "0001_customer_order_loyalty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
