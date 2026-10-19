from datetime import datetime, time
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(min_length=7, max_length=32)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    delivery_address: str | None
    profile_image_url: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    delivery_address: str | None = Field(default=None, max_length=500)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MenuItemResponse(BaseModel):
    id: str
    category_id: str
    category_name: str
    name: str
    description: str
    price_minor: int
    marked_price_minor: int | None
    image_url: str
    prep_minutes: int
    available: bool
    points_eligible: bool
    rating_average: float
    rating_count: int

    model_config = ConfigDict(from_attributes=True)


class AdminLoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^\S(?:.*\S)?$",
        validation_alias=AliasChoices("username", "email"),
    )
    password: str = Field(min_length=1, max_length=256)


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MenuItemWriteRequest(BaseModel):
    category_name: Literal["Food", "Drinks", "Bites"]
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    price_minor: int = Field(gt=0, le=100_000_000)
    marked_price_minor: int | None = Field(default=None, gt=0, le=100_000_000)
    image_url: str = Field(min_length=1, max_length=500)
    prep_minutes: int = Field(default=15, ge=1, le=600)
    available: bool = True
    points_eligible: bool = True

    @model_validator(mode="after")
    def marked_price_covers_selling_price(self):
        if self.marked_price_minor is not None and self.marked_price_minor < self.price_minor:
            raise ValueError("Marked price must be at least the selling price.")
        return self


class MenuRatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


class MenuRatingResponse(BaseModel):
    rating_average: float
    rating_count: int
    your_rating: int


class OrderLineRequest(BaseModel):
    menu_item_id: str
    quantity: int = Field(ge=1, le=20)


class CreateOrderRequest(BaseModel):
    order_type: str = Field(pattern="^(takeaway|dine_in)$")
    table_number: str | None = Field(default=None, max_length=20)
    notes: str = Field(default="", max_length=500)
    items: list[OrderLineRequest] = Field(min_length=1, max_length=30)


class OrderItemResponse(BaseModel):
    item_name: str
    unit_price_minor: int
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class PaymentResponse(BaseModel):
    id: str
    provider: str
    amount_minor: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: str
    order_number: str
    order_type: str
    table_number: str | None
    notes: str
    subtotal_minor: int
    total_minor: int
    status: str
    items: list[OrderItemResponse]
    payment: PaymentResponse | None

    model_config = ConfigDict(from_attributes=True)


class LoyaltyResponse(BaseModel):
    balance: int
    transactions: list[dict]


class LoyaltyConfigurationUpdate(BaseModel):
    standard_min_spend_kes: int = Field(ge=0, le=1_000_000)
    standard_award_points: int = Field(gt=0, le=100_000)
    standard_redeem_threshold: int = Field(gt=0, le=1_000_000)
    vip_min_spend_kes: int = Field(ge=0, le=1_000_000)
    vip_award_points: int = Field(gt=0, le=100_000)
    vip_qualification_points: int = Field(gt=0, le=1_000_000)
    weekend_days: list[Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]] = Field(min_length=1)
    weekend_start: time
    weekend_end: time
    weekend_reward_name: str = Field(min_length=2, max_length=120)
    weekend_reward_description: str = Field(max_length=500)
    timezone_name: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def valid_weekend_window(self):
        if self.weekend_start >= self.weekend_end:
            raise ValueError("Weekend serving end time must be after its start time.")
        if len(set(self.weekend_days)) != len(self.weekend_days):
            raise ValueError("Weekend days cannot contain duplicates.")
        return self


class RewardWriteRequest(BaseModel):
    menu_item_id: str | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    points_cost: int = Field(gt=0, le=1_000_000)
    conditions: str = Field(default="", max_length=500)
    available: bool = True


class LoyaltyAdjustmentRequest(BaseModel):
    track: Literal["standard", "vip"]
    points: int = Field(ge=-100_000, le=100_000)
    reason: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def nonzero_adjustment(self):
        if self.points == 0:
            raise ValueError("An adjustment must change the points balance.")
        return self


class LoyaltyVerifyRequest(BaseModel):
    code: str = Field(min_length=8, max_length=32)


class LoyaltySuspensionUpdate(BaseModel):
    suspended: bool
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_suspension_reason(self):
        if self.suspended and len(self.reason.strip()) < 5:
            raise ValueError("Provide a reason of at least 5 characters when suspending an account.")
        return self
