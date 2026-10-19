from datetime import date, datetime, time, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    loyalty_transactions: Mapped[list["LoyaltyTransaction"]] = relationship(back_populates="customer")
    loyalty_profile: Mapped["LoyaltyProfile | None"] = relationship(back_populates="customer", uselist=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[list["MenuItem"]] = relationship(back_populates="category")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    price_minor: Mapped[int] = mapped_column(Integer)
    marked_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), default="")
    prep_minutes: Mapped[int] = mapped_column(Integer, default=15)
    available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    points_eligible: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped[Category] = relationship(back_populates="items")
    ratings: Mapped[list["MenuRating"]] = relationship(back_populates="menu_item", cascade="all, delete-orphan")

    @property
    def category_name(self) -> str:
        return self.category.name

    @property
    def rating_average(self) -> float:
        return round(sum(rating.rating for rating in self.ratings) / len(self.ratings), 1) if self.ratings else 0

    @property
    def rating_count(self) -> int:
        return len(self.ratings)


class MenuRating(Base):
    __tablename__ = "menu_ratings"
    __table_args__ = (UniqueConstraint("menu_item_id", "customer_id", name="uq_menu_rating_customer_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    menu_item: Mapped[MenuItem] = relationship(back_populates="ratings")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    order_type: Mapped[str] = mapped_column(String(20), default="takeaway")
    table_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="")
    subtotal_minor: Mapped[int] = mapped_column(Integer)
    total_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending_payment", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    customer: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payment: Mapped["Payment | None"] = relationship(back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    item_name: Mapped[str] = mapped_column(String(120))
    unit_price_minor: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    points_eligible: Mapped[bool] = mapped_column(Boolean)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(30), default="demo")
    provider_reference: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship(back_populates="payment")


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_loyalty_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    transaction_type: Mapped[str] = mapped_column(String(20))
    track: Mapped[str] = mapped_column(String(20), default="standard", index=True)
    points: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200))
    admin_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    customer: Mapped[User] = relationship(back_populates="loyalty_transactions")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    menu_item_id: Mapped[str | None] = mapped_column(ForeignKey("menu_items.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    points_cost: Mapped[int] = mapped_column(Integer)
    conditions: Mapped[str] = mapped_column(String(500), default="")
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class LoyaltyProfile(Base):
    __tablename__ = "loyalty_profiles"

    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vip_membership_number: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    vip_qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer: Mapped[User] = relationship(back_populates="loyalty_profile")


class LoyaltyConfiguration(Base):
    __tablename__ = "loyalty_configuration"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    standard_min_spend_minor: Mapped[int] = mapped_column(Integer, default=20_000)
    standard_award_points: Mapped[int] = mapped_column(Integer, default=5)
    standard_redeem_threshold: Mapped[int] = mapped_column(Integer, default=200)
    vip_min_spend_minor: Mapped[int] = mapped_column(Integer, default=100_000)
    vip_award_points: Mapped[int] = mapped_column(Integer, default=10)
    vip_qualification_points: Mapped[int] = mapped_column(Integer, default=100)
    weekend_days: Mapped[str] = mapped_column(String(80), default="Saturday,Sunday")
    weekend_start: Mapped[time] = mapped_column(Time, default=time(12, 0))
    weekend_end: Mapped[time] = mapped_column(Time, default=time(22, 0))
    weekend_reward_name: Mapped[str] = mapped_column(String(120), default="Complimentary nyama choma")
    weekend_reward_description: Mapped[str] = mapped_column(String(500), default="One complimentary portion per eligible VIP per weekend.")
    timezone_name: Mapped[str] = mapped_column(String(64), default="Africa/Nairobi")


class RewardRedemption(Base):
    __tablename__ = "reward_redemptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reward_id: Mapped[str] = mapped_column(ForeignKey("rewards.id"), index=True)
    points_cost: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class WeekendBenefitClaim(Base):
    __tablename__ = "weekend_benefit_claims"
    __table_args__ = (UniqueConstraint("customer_id", "weekend_key", name="uq_vip_weekend_claim_customer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    weekend_key: Mapped[date] = mapped_column(Date, index=True)
    reward_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admin_actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(500), default="")
    details: Mapped[str] = mapped_column(String(2000), default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
