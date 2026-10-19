"""Add persistent customer sessions for refresh-token authentication.

Revision ID: 0006_customer_sessions
Revises: 0005_customer_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_customer_sessions"
down_revision = "0005_customer_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index(
        op.f("ix_customer_sessions_refresh_token_hash"),
        "customer_sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_customer_sessions_user_id"),
        "customer_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_sessions_user_id"), table_name="customer_sessions")
    op.drop_index(op.f("ix_customer_sessions_refresh_token_hash"), table_name="customer_sessions")
    op.drop_table("customer_sessions")
