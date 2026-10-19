"""Add configurable standard and VIP loyalty rewards.

Revision ID: 0004_loyalty_system
Revises: 0003_managed_menu
"""
from alembic import context, op
import sqlalchemy as sa

revision = "0004_loyalty_system"
down_revision = "0003_managed_menu"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return False if context.is_offline_mode() else sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, name: str) -> bool:
    return not context.is_offline_mode() and any(
        column["name"] == name for column in sa.inspect(op.get_bind()).get_columns(table)
    )


def _ensure_index(name: str, table: str, columns: list[str]) -> None:
    if context.is_offline_mode() or not any(
        index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table)
    ):
        op.create_index(name, table, columns)


def _has_menu_item_foreign_key() -> bool:
    return not context.is_offline_mode() and any(
        foreign_key["constrained_columns"] == ["menu_item_id"]
        and foreign_key["referred_table"] == "menu_items"
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("rewards")
    )


def upgrade() -> None:
    for name, column in (
        ("track", sa.Column("track", sa.String(length=20), nullable=False, server_default="standard")),
        ("admin_actor", sa.Column("admin_actor", sa.String(length=255), nullable=True)),
        ("reason", sa.Column("reason", sa.String(length=500), nullable=True)),
    ):
        if not _has_column("loyalty_transactions", name):
            op.add_column("loyalty_transactions", column)
    _ensure_index("ix_loyalty_transactions_track", "loyalty_transactions", ["track"])

    if not _has_column("rewards", "menu_item_id"):
        op.add_column("rewards", sa.Column("menu_item_id", sa.String(length=36), nullable=True))
    if not _has_column("rewards", "conditions"):
        op.add_column("rewards", sa.Column("conditions", sa.String(length=500), nullable=False, server_default=""))
    if not _has_menu_item_foreign_key():
        op.create_foreign_key("fk_rewards_menu_item_id_menu_items", "rewards", "menu_items", ["menu_item_id"], ["id"])
    _ensure_index("ix_rewards_menu_item_id", "rewards", ["menu_item_id"])

    if not _has_table("loyalty_profiles"):
        op.create_table(
            "loyalty_profiles",
            sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("vip_membership_number", sa.String(length=30), nullable=True, unique=True),
            sa.Column("vip_qualified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("suspension_reason", sa.String(length=500), nullable=True),
        )
    op.execute(
        sa.text(
            "INSERT INTO loyalty_profiles (customer_id) "
            "SELECT id FROM users ON CONFLICT (customer_id) DO NOTHING"
        )
    )
    if not _has_table("loyalty_configuration"):
        op.create_table(
            "loyalty_configuration",
            sa.Column("id", sa.String(length=20), primary_key=True),
            sa.Column("standard_min_spend_minor", sa.Integer(), nullable=False, server_default="20000"),
            sa.Column("standard_award_points", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("standard_redeem_threshold", sa.Integer(), nullable=False, server_default="200"),
            sa.Column("vip_min_spend_minor", sa.Integer(), nullable=False, server_default="100000"),
            sa.Column("vip_award_points", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("vip_qualification_points", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("weekend_days", sa.String(length=80), nullable=False, server_default="Saturday,Sunday"),
            sa.Column("weekend_start", sa.Time(), nullable=False, server_default="12:00:00"),
            sa.Column("weekend_end", sa.Time(), nullable=False, server_default="22:00:00"),
            sa.Column("weekend_reward_name", sa.String(length=120), nullable=False, server_default="Complimentary nyama choma"),
            sa.Column(
                "weekend_reward_description",
                sa.String(length=500),
                nullable=False,
                server_default="One complimentary portion per eligible VIP per weekend.",
            ),
            sa.Column("timezone_name", sa.String(length=64), nullable=False, server_default="Africa/Nairobi"),
        )
    op.execute(
        sa.text(
            "INSERT INTO loyalty_configuration (id, standard_min_spend_minor, standard_award_points, "
            "standard_redeem_threshold, vip_min_spend_minor, vip_award_points, vip_qualification_points, "
            "weekend_days, weekend_start, weekend_end, weekend_reward_name, weekend_reward_description, timezone_name) "
            "VALUES ('default', 20000, 5, 200, 100000, 10, 100, 'Saturday,Sunday', '12:00:00', '22:00:00', "
            "'Complimentary nyama choma', 'One complimentary portion per eligible VIP per weekend.', 'Africa/Nairobi') "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    if not _has_table("reward_redemptions"):
        op.create_table(
            "reward_redemptions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("code", sa.String(length=32), nullable=False, unique=True),
            sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reward_id", sa.String(length=36), sa.ForeignKey("rewards.id"), nullable=False),
            sa.Column("points_cost", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("redeemed_by", sa.String(length=255), nullable=True),
        )
    for name, columns in (
        ("ix_reward_redemptions_code", ["code"]),
        ("ix_reward_redemptions_customer_id", ["customer_id"]),
        ("ix_reward_redemptions_reward_id", ["reward_id"]),
        ("ix_reward_redemptions_status", ["status"]),
    ):
        _ensure_index(name, "reward_redemptions", columns)

    if not _has_table("weekend_benefit_claims"):
        op.create_table(
            "weekend_benefit_claims",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("code", sa.String(length=32), nullable=False, unique=True),
            sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("weekend_key", sa.Date(), nullable=False),
            sa.Column("reward_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("redeemed_by", sa.String(length=255), nullable=True),
            sa.UniqueConstraint("customer_id", "weekend_key", name="uq_vip_weekend_claim_customer"),
        )
    for name, columns in (
        ("ix_weekend_benefit_claims_code", ["code"]),
        ("ix_weekend_benefit_claims_customer_id", ["customer_id"]),
        ("ix_weekend_benefit_claims_weekend_key", ["weekend_key"]),
        ("ix_weekend_benefit_claims_status", ["status"]),
    ):
        _ensure_index(name, "weekend_benefit_claims", columns)

    if not _has_table("admin_audit_logs"):
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("admin_actor", sa.String(length=255), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=100), nullable=False),
            sa.Column("reason", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("details", sa.String(length=2000), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    _ensure_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    _ensure_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_weekend_benefit_claims_status", table_name="weekend_benefit_claims")
    op.drop_index("ix_weekend_benefit_claims_weekend_key", table_name="weekend_benefit_claims")
    op.drop_index("ix_weekend_benefit_claims_customer_id", table_name="weekend_benefit_claims")
    op.drop_index("ix_weekend_benefit_claims_code", table_name="weekend_benefit_claims")
    op.drop_table("weekend_benefit_claims")
    op.drop_index("ix_reward_redemptions_status", table_name="reward_redemptions")
    op.drop_index("ix_reward_redemptions_reward_id", table_name="reward_redemptions")
    op.drop_index("ix_reward_redemptions_customer_id", table_name="reward_redemptions")
    op.drop_index("ix_reward_redemptions_code", table_name="reward_redemptions")
    op.drop_table("reward_redemptions")
    op.drop_table("loyalty_configuration")
    op.drop_table("loyalty_profiles")
    op.drop_index("ix_rewards_menu_item_id", table_name="rewards")
    op.drop_constraint("fk_rewards_menu_item_id_menu_items", "rewards", type_="foreignkey")
    op.drop_column("rewards", "conditions")
    op.drop_column("rewards", "menu_item_id")
    op.drop_index("ix_loyalty_transactions_track", table_name="loyalty_transactions")
    op.drop_column("loyalty_transactions", "reason")
    op.drop_column("loyalty_transactions", "admin_actor")
    op.drop_column("loyalty_transactions", "track")
