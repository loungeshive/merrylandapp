from contextlib import asynccontextmanager
import csv
from datetime import datetime, timedelta, timezone
import hmac
import io
import json
import secrets
import re
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.google_auth import GoogleVerificationUnavailable, verify_google_id_token
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import (
    AdminAuditLog,
    Category,
    LoyaltyConfiguration,
    LoyaltyProfile,
    LoyaltyTransaction,
    MenuItem,
    MenuRating,
    Order,
    OrderItem,
    Payment,
    Reward,
    RewardRedemption,
    User,
    WeekendBenefitClaim,
)
from app.db.session import Base, SessionLocal, engine, get_db
from app.api.schemas import (
    AdminLoginRequest,
    AdminTokenResponse,
    CreateOrderRequest,
    GoogleAuthRequest,
    LoyaltyAdjustmentRequest,
    LoyaltyConfigurationUpdate,
    LoyaltySuspensionUpdate,
    LoyaltyVerifyRequest,
    LoginRequest,
    MenuItemResponse,
    MenuItemWriteRequest,
    MenuRatingRequest,
    MenuRatingResponse,
    OrderResponse,
    RewardWriteRequest,
    RegisterRequest,
    TokenResponse,
    UserProfileUpdate,
    UserResponse,
)

auth_scheme = HTTPBearer(auto_error=False)
UPLOAD_DIR = Path(settings.upload_directory)
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = Path(__file__).resolve().parents[2] / UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def seed_menu() -> None:
    with SessionLocal() as db:
        for sort_order, name in enumerate(("Food", "Drinks", "Bites"), start=1):
            if db.scalar(select(Category.id).where(Category.name == name)) is None:
                db.add(Category(name=name, sort_order=sort_order))
        if db.get(LoyaltyConfiguration, "default") is None:
            db.add(LoyaltyConfiguration(id="default"))
        db.commit()


def loyalty_configuration(db: Session) -> LoyaltyConfiguration:
    configuration = db.get(LoyaltyConfiguration, "default")
    if configuration is None:
        raise HTTPException(status_code=503, detail="Loyalty configuration is missing. Apply the database migration.")
    return configuration


def ledger_points(db: Session, customer_id: str, track: str, transaction_type: str | None = None) -> int:
    query = select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(
        LoyaltyTransaction.customer_id == customer_id,
        LoyaltyTransaction.track == track,
    )
    if transaction_type is not None:
        query = query.where(LoyaltyTransaction.transaction_type == transaction_type)
    return int(db.scalar(query) or 0)


def ensure_loyalty_profile(db: Session, customer_id: str, *, lock: bool = False) -> LoyaltyProfile:
    query = select(LoyaltyProfile).where(LoyaltyProfile.customer_id == customer_id)
    if lock:
        query = query.with_for_update()
    profile = db.scalar(query)
    if profile is None:
        profile = LoyaltyProfile(customer_id=customer_id)
        db.add(profile)
        db.flush()
    return profile


def ensure_vip_qualification(db: Session, customer_id: str, configuration: LoyaltyConfiguration) -> LoyaltyProfile:
    db.scalar(select(User.id).where(User.id == customer_id).with_for_update())
    profile = ensure_loyalty_profile(db, customer_id, lock=True)
    earned = ledger_points(db, customer_id, "vip", "earned")
    if earned >= configuration.vip_qualification_points and profile.vip_qualified_at is None:
        profile.vip_qualified_at = datetime.now(timezone.utc)
        profile.vip_membership_number = f"MR-VIP-{secrets.token_hex(5).upper()}"
    return profile


def award_paid_order_points(db: Session, order: Order) -> None:
    configuration = loyalty_configuration(db)
    eligible_spend = sum(
        item.unit_price_minor * item.quantity
        for item in order.items
        if item.points_eligible
    )
    awards = (
        (
            "standard",
            configuration.standard_min_spend_minor,
            configuration.standard_award_points,
            "Standard points",
        ),
        ("vip", configuration.vip_min_spend_minor, configuration.vip_award_points, "VIP points"),
    )
    for track, minimum_spend, award_points, description in awards:
        if eligible_spend <= minimum_spend:
            continue
        idempotency_key = f"paid-order:{order.id}:{track}"
        existing = db.scalar(
            select(LoyaltyTransaction.id).where(LoyaltyTransaction.idempotency_key == idempotency_key)
        )
        if existing is None:
            db.add(
                LoyaltyTransaction(
                    customer_id=order.customer_id,
                    order_id=order.id,
                    idempotency_key=idempotency_key,
                    transaction_type="earned",
                    track=track,
                    points=award_points,
                    description=f"{description} earned for order {order.order_number}",
                )
            )
    db.flush()
    ensure_vip_qualification(db, order.customer_id, configuration)


def available_standard_points(db: Session, customer_id: str, *, exclude_redemption_id: str | None = None) -> int:
    reserved_query = select(func.coalesce(func.sum(RewardRedemption.points_cost), 0)).where(
        RewardRedemption.customer_id == customer_id,
        RewardRedemption.status == "pending",
    )
    if exclude_redemption_id is not None:
        reserved_query = reserved_query.where(RewardRedemption.id != exclude_redemption_id)
    reserved = int(db.scalar(reserved_query) or 0)
    return ledger_points(db, customer_id, "standard") - reserved


def loyalty_code() -> str:
    return f"MR-{secrets.token_hex(6).upper()}"


def add_admin_audit_log(
    db: Session,
    admin: str,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    reason: str = "",
    details: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_actor=admin,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            details=json.dumps(details or {}, ensure_ascii=True, separators=(",", ":")),
        )
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env.lower() != "test" and not settings.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ):
        raise RuntimeError("Configure DATABASE_URL to use Neon PostgreSQL. SQLite is supported only for automated tests.")
    if settings.app_env.lower() == "production":
        if settings.demo_payment_enabled:
            raise RuntimeError("The demo payment adapter must be disabled in production.")
        if len(settings.jwt_secret) < 32 or "development" in settings.jwt_secret.lower():
            raise RuntimeError("Set a strong production JWT_SECRET before starting the API.")
    elif settings.app_env.lower() == "test":
        Base.metadata.create_all(bind=engine)
        seed_menu()
    yield


app = FastAPI(
    title="Merryland Dining & Rewards API",
    version="0.1.0",
    description="Shared API for the Merryland web and mobile clients.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("sub")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.") from exc
    if payload.get("role", "customer") != "customer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Customer sign-in required.")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found.")
    return user


def current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
) -> str:
    if not settings.admin_username.strip() or not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin sign-in has not been configured.")
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in with the administrator account.")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired admin session.") from exc
    if payload.get("role") != "admin" or payload.get("sub") != settings.admin_username.strip().lower():
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return settings.admin_username.strip().lower()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/admin/auth/login", response_model=AdminTokenResponse)
def admin_login(payload: AdminLoginRequest) -> AdminTokenResponse:
    configured_username = settings.admin_username.strip().lower()
    if not configured_username or not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin sign-in has not been configured.")
    username_matches = hmac.compare_digest(payload.username.strip().lower(), configured_username)
    password_matches = hmac.compare_digest(
        payload.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
    if not username_matches or not password_matches:
        raise HTTPException(status_code=401, detail="Administrator username or password is incorrect.")
    return AdminTokenResponse(access_token=create_access_token(configured_username, role="admin"))


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = User(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        phone=payload.phone.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with that email or phone already exists.") from exc
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or user.password_hash is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@app.post("/api/v1/auth/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    allowed_client_ids = settings.google_allowed_client_ids
    if not allowed_client_ids:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        claims = verify_google_id_token(payload.id_token, allowed_client_ids)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified.") from exc
    except GoogleVerificationUnavailable as exc:
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable.") from exc

    subject = claims.get("sub")
    email = claims.get("email")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        or claims.get("email_verified") is not True
    ):
        raise HTTPException(status_code=401, detail="Google must provide a verified email address.")

    email = email.strip().lower()
    name = claims.get("name")
    if not isinstance(name, str) or not name.strip():
        name = email.partition("@")[0]

    user = db.scalar(select(User).where(User.google_sub == subject))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and user.google_sub not in (None, subject):
            raise HTTPException(status_code=409, detail="This email is linked to a different Google account.")
        if user is None:
            user = User(name=name.strip()[:120], email=email, phone=None, password_hash=None, google_sub=subject)
            db.add(user)
        else:
            user.google_sub = subject
    elif user.email != email:
        email_owner = db.scalar(select(User).where(User.email == email))
        if email_owner is not None and email_owner.id != user.id:
            raise HTTPException(status_code=409, detail="This Google email belongs to a different account.")
        user.email = email

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        linked_user = db.scalar(select(User).where(User.google_sub == subject))
        if linked_user is None:
            raise HTTPException(status_code=409, detail="This Google account could not be linked.") from exc
        user = linked_user
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@app.get("/api/v1/auth/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.patch("/api/v1/auth/me", response_model=UserResponse)
def update_my_profile(
    payload: UserProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Enter your full name.")
    phone = payload.phone.strip() if payload.phone and payload.phone.strip() else None
    user.name = name
    user.phone = phone
    user.delivery_address = payload.delivery_address.strip() if payload.delivery_address and payload.delivery_address.strip() else None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That phone number is already linked to another account.") from exc
    db.refresh(user)
    return user


def save_uploaded_image(image: UploadFile, content: bytes) -> tuple[str, Path]:
    formats = {
        "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
        "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
        "image/webp": (".webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
    }
    image_format = formats.get(image.content_type or "")
    if image_format is None:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, or WebP image.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    extension, validate_signature = image_format
    if not validate_signature(content):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid image.")
    path = UPLOAD_DIR / f"{uuid4().hex}{extension}"
    path.write_bytes(content)
    return f"{path.name}", path


async def read_image_upload(image: UploadFile) -> bytes:
    content = await image.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    return content


def owned_profile_image_path(image_url: str | None) -> Path | None:
    if not image_url:
        return None
    filename = Path(urlsplit(image_url).path).name
    if not re.fullmatch(r"[0-9a-f]{32}\.(?:jpg|png|webp)", filename):
        return None
    image_path = UPLOAD_DIR / filename
    return image_path if image_path.is_file() else None


@app.post("/api/v1/auth/me/photo", response_model=UserResponse)
async def upload_my_profile_photo(
    request: Request,
    image: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    content = await read_image_upload(image)
    filename, image_path = save_uploaded_image(image, content)
    previous_image = owned_profile_image_path(user.profile_image_url)
    user.profile_image_url = f"{str(request.base_url).rstrip('/')}/uploads/{filename}"
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        image_path.unlink(missing_ok=True)
        raise
    db.refresh(user)
    if previous_image is not None and previous_image != image_path:
        previous_image.unlink(missing_ok=True)
    return user


@app.delete("/api/v1/auth/me/photo", status_code=204)
def delete_my_profile_photo(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    image_path = owned_profile_image_path(user.profile_image_url)
    user.profile_image_url = None
    db.commit()
    if image_path is not None:
        image_path.unlink(missing_ok=True)
    return Response(status_code=204)


@app.get("/api/v1/menu", response_model=list[MenuItemResponse])
def menu(db: Session = Depends(get_db)) -> list[MenuItem]:
    return list(
        db.scalars(
            select(MenuItem)
            .join(Category)
            .options(joinedload(MenuItem.category), selectinload(MenuItem.ratings))
            .where(MenuItem.available.is_(True), Category.active.is_(True))
            .order_by(Category.sort_order, MenuItem.name)
        )
    )


@app.get("/api/v1/admin/menu", response_model=list[MenuItemResponse])
def admin_menu(
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[MenuItem]:
    return list(
        db.scalars(
            select(MenuItem)
            .options(joinedload(MenuItem.category), selectinload(MenuItem.ratings))
            .order_by(MenuItem.available.desc(), MenuItem.name)
        )
    )


@app.post("/api/v1/admin/menu/images", status_code=201)
async def upload_menu_image(
    request: Request,
    image: UploadFile = File(...),
    _: str = Depends(current_admin),
) -> dict[str, str]:
    content = await read_image_upload(image)
    filename, _ = save_uploaded_image(image, content)
    return {"image_url": f"{str(request.base_url).rstrip('/')}/uploads/{filename}"}


def category_for_menu_write(category_name: str, db: Session) -> Category:
    category = db.scalar(select(Category).where(Category.name == category_name, Category.active.is_(True)))
    if category is None:
        raise HTTPException(status_code=422, detail="Choose Food, Drinks, or Bites.")
    return category


@app.post("/api/v1/admin/menu", response_model=MenuItemResponse, status_code=201)
def create_menu_item(
    payload: MenuItemWriteRequest,
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> MenuItem:
    item = MenuItem(
        category=category_for_menu_write(payload.category_name, db),
        name=payload.name.strip(),
        description=payload.description.strip(),
        price_minor=payload.price_minor,
        marked_price_minor=payload.marked_price_minor,
        image_url=payload.image_url,
        prep_minutes=payload.prep_minutes,
        available=payload.available,
        points_eligible=payload.points_eligible,
    )
    db.add(item)
    db.commit()
    return db.scalar(
        select(MenuItem).options(joinedload(MenuItem.category), selectinload(MenuItem.ratings)).where(MenuItem.id == item.id)
    )


@app.put("/api/v1/admin/menu/{menu_item_id}", response_model=MenuItemResponse)
def update_menu_item(
    menu_item_id: str,
    payload: MenuItemWriteRequest,
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> MenuItem:
    item = db.get(MenuItem, menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Menu item not found.")
    item.category = category_for_menu_write(payload.category_name, db)
    item.name = payload.name.strip()
    item.description = payload.description.strip()
    item.price_minor = payload.price_minor
    item.marked_price_minor = payload.marked_price_minor
    item.image_url = payload.image_url
    item.prep_minutes = payload.prep_minutes
    item.available = payload.available
    item.points_eligible = payload.points_eligible
    db.commit()
    return db.scalar(
        select(MenuItem).options(joinedload(MenuItem.category), selectinload(MenuItem.ratings)).where(MenuItem.id == item.id)
    )


@app.delete("/api/v1/admin/menu/{menu_item_id}", status_code=204)
def delete_menu_item(
    menu_item_id: str,
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> None:
    item = db.get(MenuItem, menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Menu item not found.")
    item.available = False
    db.commit()


@app.post("/api/v1/menu/{menu_item_id}/ratings", response_model=MenuRatingResponse)
def rate_menu_item(
    menu_item_id: str,
    payload: MenuRatingRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MenuRatingResponse:
    item = db.scalar(
        select(MenuItem).where(MenuItem.id == menu_item_id, MenuItem.available.is_(True)).with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Menu item not found.")
    rating = db.scalar(
        select(MenuRating).where(MenuRating.menu_item_id == menu_item_id, MenuRating.customer_id == user.id)
    )
    if rating is None:
        rating = MenuRating(menu_item_id=menu_item_id, customer_id=user.id, rating=payload.rating)
        db.add(rating)
    else:
        rating.rating = payload.rating
        rating.updated_at = datetime.now(timezone.utc)
    db.commit()
    average, count = db.execute(
        select(func.avg(MenuRating.rating), func.count(MenuRating.id)).where(MenuRating.menu_item_id == menu_item_id)
    ).one()
    return MenuRatingResponse(
        rating_average=round(float(average or 0), 1),
        rating_count=count,
        your_rating=payload.rating,
    )


@app.post("/api/v1/orders", response_model=OrderResponse, status_code=201)
def create_order(
    payload: CreateOrderRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Order:
    if payload.order_type == "dine_in" and not payload.table_number:
        raise HTTPException(status_code=422, detail="A table number is required for dine-in orders.")
    ids = [line.menu_item_id for line in payload.items]
    products = {
        item.id: item
        for item in db.scalars(select(MenuItem).where(MenuItem.id.in_(ids), MenuItem.available.is_(True)))
    }
    if len(products) != len(set(ids)):
        raise HTTPException(status_code=409, detail="One or more menu items are unavailable.")
    subtotal = sum(products[line.menu_item_id].price_minor * line.quantity for line in payload.items)
    order = Order(
        order_number=f"MR-{secrets.token_hex(4).upper()}",
        customer_id=user.id,
        order_type=payload.order_type,
        table_number=payload.table_number,
        notes=payload.notes.strip(),
        subtotal_minor=subtotal,
        total_minor=subtotal,
        status="pending_payment",
    )
    for line in payload.items:
        item = products[line.menu_item_id]
        order.items.append(
            OrderItem(
                menu_item_id=item.id,
                item_name=item.name,
                unit_price_minor=item.price_minor,
                quantity=line.quantity,
                points_eligible=item.points_eligible,
            )
        )
    order.payment = Payment(amount_minor=subtotal, status="pending", provider="demo")
    db.add(order)
    db.commit()
    return db.execute(
        select(Order).options(joinedload(Order.items), joinedload(Order.payment)).where(Order.id == order.id)
    ).unique().scalar_one()


@app.post("/api/v1/payments/{payment_id}/simulate-success", response_model=OrderResponse)
def simulate_payment_success(
    payment_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Order:
    if settings.app_env.lower() == "production" or not settings.demo_payment_enabled:
        raise HTTPException(status_code=404, detail="Not found.")
    payment = db.scalar(
        select(Payment)
        .join(Order)
        .where(Payment.id == payment_id, Order.customer_id == user.id)
        .with_for_update()
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    order = db.scalar(
        select(Order).options(joinedload(Order.items)).where(Order.id == payment.order_id).with_for_update()
    )
    if payment.status == "pending":
        payment.status = "succeeded"
        payment.provider_reference = f"DEV-{payment.id}"
        payment.confirmed_at = datetime.now(timezone.utc)
        order.status = "confirmed"
        award_paid_order_points(db, order)
        db.commit()
    return db.execute(
        select(Order)
        .options(joinedload(Order.items), joinedload(Order.payment))
        .where(Order.id == order.id)
    ).unique().scalar_one()


@app.get("/api/v1/orders", response_model=list[OrderResponse])
def my_orders(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .options(joinedload(Order.items), joinedload(Order.payment))
            .where(Order.customer_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(50)
        ).unique()
    )


@app.get("/api/v1/loyalty/balance")
def loyalty_balance(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    entries = list(
        db.scalars(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.customer_id == user.id)
            .order_by(LoyaltyTransaction.created_at.desc())
        )
    )
    return {
        "balance": ledger_points(db, user.id, "standard"),
        "vip_balance": ledger_points(db, user.id, "vip"),
        "transactions": [
            {
                "id": entry.id,
                "type": entry.transaction_type,
                "track": entry.track,
                "points": entry.points,
                "description": entry.description,
                "reason": entry.reason,
                "created_at": entry.created_at,
            }
            for entry in entries
        ],
    }


def configuration_response(configuration: LoyaltyConfiguration) -> dict:
    return {
        "standard_min_spend_kes": configuration.standard_min_spend_minor // 100,
        "standard_award_points": configuration.standard_award_points,
        "standard_redeem_threshold": configuration.standard_redeem_threshold,
        "vip_min_spend_kes": configuration.vip_min_spend_minor // 100,
        "vip_award_points": configuration.vip_award_points,
        "vip_qualification_points": configuration.vip_qualification_points,
        "weekend_days": configuration.weekend_days.split(","),
        "weekend_start": configuration.weekend_start.isoformat(timespec="minutes"),
        "weekend_end": configuration.weekend_end.isoformat(timespec="minutes"),
        "weekend_reward_name": configuration.weekend_reward_name,
        "weekend_reward_description": configuration.weekend_reward_description,
        "timezone_name": configuration.timezone_name,
    }


def reward_response(db: Session, reward: Reward) -> dict:
    product = db.get(MenuItem, reward.menu_item_id) if reward.menu_item_id else None
    return {
        "id": reward.id,
        "menu_item_id": reward.menu_item_id,
        "name": reward.name,
        "description": reward.description,
        "points_cost": reward.points_cost,
        "conditions": reward.conditions,
        "available": reward.available and (product is None or product.available),
        "image_url": product.image_url if product else "",
        "price_minor": product.price_minor if product else None,
    }


def redemption_response(db: Session, redemption: RewardRedemption) -> dict:
    reward = db.get(Reward, redemption.reward_id)
    return {
        "id": redemption.id,
        "code": redemption.code,
        "reward_id": redemption.reward_id,
        "reward_name": reward.name if reward else "Reward",
        "points_cost": redemption.points_cost,
        "status": redemption.status,
        "created_at": redemption.created_at,
        "redeemed_at": redemption.redeemed_at,
    }


def weekend_claim_response(claim: WeekendBenefitClaim) -> dict:
    return {
        "id": claim.id,
        "code": claim.code,
        "weekend_key": claim.weekend_key,
        "reward_name": claim.reward_name,
        "status": claim.status,
        "created_at": claim.created_at,
        "redeemed_at": claim.redeemed_at,
    }


@app.get("/api/v1/loyalty/dashboard")
def loyalty_dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    configuration = loyalty_configuration(db)
    profile = ensure_vip_qualification(db, user.id, configuration)
    db.commit()
    standard_balance = available_standard_points(db, user.id)
    standard_earned = ledger_points(db, user.id, "standard", "earned")
    vip_balance = ledger_points(db, user.id, "vip")
    vip_earned = ledger_points(db, user.id, "vip", "earned")
    local_now = datetime.now(ZoneInfo(configuration.timezone_name))
    weekend_key = local_now.date() - timedelta(days=local_now.weekday())
    weekend_claim = db.scalar(
        select(WeekendBenefitClaim).where(
            WeekendBenefitClaim.customer_id == user.id,
            WeekendBenefitClaim.weekend_key == weekend_key,
        )
    )
    eligible_day = local_now.strftime("%A") in configuration.weekend_days.split(",")
    within_hours = configuration.weekend_start <= local_now.time().replace(tzinfo=None) <= configuration.weekend_end
    active_vip = profile.vip_qualified_at is not None and profile.suspended_at is None
    rewards = list(db.scalars(select(Reward).where(Reward.available.is_(True)).order_by(Reward.points_cost, Reward.name)))
    redemptions = list(
        db.scalars(
            select(RewardRedemption)
            .where(RewardRedemption.customer_id == user.id)
            .order_by(RewardRedemption.created_at.desc())
            .limit(50)
        )
    )
    claims = list(
        db.scalars(
            select(WeekendBenefitClaim)
            .where(WeekendBenefitClaim.customer_id == user.id)
            .order_by(WeekendBenefitClaim.created_at.desc())
            .limit(20)
        )
    )
    transactions = list(
        db.scalars(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.customer_id == user.id)
            .order_by(LoyaltyTransaction.created_at.desc())
            .limit(100)
        )
    )
    orders = list(
        db.scalars(
            select(Order)
            .join(Payment)
            .options(joinedload(Order.payment), selectinload(Order.items))
            .where(Order.customer_id == user.id, Payment.status == "succeeded")
            .order_by(Order.created_at.desc())
            .limit(50)
        ).unique()
    )
    order_awards = {order.id: {"standard": 0, "vip": 0} for order in orders}
    if order_awards:
        for entry in db.scalars(
            select(LoyaltyTransaction).where(
                LoyaltyTransaction.customer_id == user.id,
                LoyaltyTransaction.order_id.in_(order_awards),
                LoyaltyTransaction.transaction_type == "earned",
            )
        ):
            if entry.track in ("standard", "vip"):
                order_awards[entry.order_id][entry.track] += entry.points
    return {
        "standard": {
            "balance": standard_balance,
            "lifetime_earned": standard_earned,
            "redeem_threshold": configuration.standard_redeem_threshold,
            "progress": min(standard_balance, configuration.standard_redeem_threshold),
            "rewards": [reward_response(db, reward) for reward in rewards],
        },
        "vip": {
            "balance": vip_balance,
            "lifetime_earned": vip_earned,
            "qualification_threshold": configuration.vip_qualification_points,
            "progress": min(vip_earned, configuration.vip_qualification_points),
            "qualified": profile.vip_qualified_at is not None,
            "membership_number": profile.vip_membership_number,
            "status": "Suspended" if profile.suspended_at else "Active" if active_vip else "Not Yet Qualified",
            "qualified_at": profile.vip_qualified_at,
            "weekend_benefit": {
                "name": configuration.weekend_reward_name,
                "description": configuration.weekend_reward_description,
                "days": configuration.weekend_days.split(","),
                "start": configuration.weekend_start,
                "end": configuration.weekend_end,
                "timezone": configuration.timezone_name,
                "claim_available": active_vip and eligible_day and within_hours and weekend_claim is None,
                "current_claim": weekend_claim_response(weekend_claim) if weekend_claim else None,
            },
            "claims": [weekend_claim_response(claim) for claim in claims],
        },
        "redemptions": [redemption_response(db, redemption) for redemption in redemptions],
        "transactions": [
            {
                "id": entry.id,
                "track": entry.track,
                "type": entry.transaction_type,
                "points": entry.points,
                "description": entry.description,
                "reason": entry.reason,
                "created_at": entry.created_at,
            }
            for entry in transactions
        ],
        "orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "total_minor": order.total_minor,
                "created_at": order.created_at,
                "standard_points": order_awards[order.id]["standard"],
                "vip_points": order_awards[order.id]["vip"],
            }
            for order in orders
        ],
    }


@app.post("/api/v1/loyalty/rewards/{reward_id}/redeem", status_code=201)
def redeem_reward(
    reward_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    profile = ensure_loyalty_profile(db, user.id)
    if profile.suspended_at is not None:
        raise HTTPException(status_code=403, detail="Your loyalty account is suspended.")
    configuration = loyalty_configuration(db)
    reward = db.scalar(select(Reward).where(Reward.id == reward_id, Reward.available.is_(True)).with_for_update())
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward is unavailable.")
    if reward.menu_item_id:
        product = db.get(MenuItem, reward.menu_item_id)
        if product is None or not product.available:
            raise HTTPException(status_code=404, detail="Reward is unavailable.")
    balance = available_standard_points(db, user.id)
    if balance < configuration.standard_redeem_threshold:
        raise HTTPException(status_code=409, detail=f"Reach {configuration.standard_redeem_threshold} points to unlock rewards.")
    if balance < reward.points_cost:
        raise HTTPException(status_code=409, detail="You do not have enough available points for this reward.")
    redemption = RewardRedemption(
        code=loyalty_code(),
        customer_id=user.id,
        reward_id=reward.id,
        points_cost=reward.points_cost,
        status="pending",
    )
    db.add(redemption)
    db.commit()
    return redemption_response(db, redemption)


@app.post("/api/v1/loyalty/redemptions/{redemption_id}/cancel")
def cancel_reward_redemption(
    redemption_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    redemption = db.scalar(
        select(RewardRedemption)
        .where(RewardRedemption.id == redemption_id, RewardRedemption.customer_id == user.id)
        .with_for_update()
    )
    if redemption is None:
        raise HTTPException(status_code=404, detail="Reward redemption not found.")
    if redemption.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending reward redemptions can be cancelled.")
    redemption.status = "cancelled"
    db.commit()
    return redemption_response(db, redemption)


@app.post("/api/v1/loyalty/vip/weekend/claim", status_code=201)
def claim_vip_weekend_benefit(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    configuration = loyalty_configuration(db)
    profile = ensure_vip_qualification(db, user.id, configuration)
    if profile.vip_qualified_at is None or profile.suspended_at is not None:
        raise HTTPException(status_code=403, detail="An active VIP membership is required for this benefit.")
    local_now = datetime.now(ZoneInfo(configuration.timezone_name))
    if (
        local_now.strftime("%A") not in configuration.weekend_days.split(",")
        or not configuration.weekend_start <= local_now.time().replace(tzinfo=None) <= configuration.weekend_end
    ):
        raise HTTPException(status_code=409, detail="VIP nyama choma claims are not available at this time.")
    weekend_key = local_now.date() - timedelta(days=local_now.weekday())
    existing = db.scalar(
        select(WeekendBenefitClaim).where(
            WeekendBenefitClaim.customer_id == user.id,
            WeekendBenefitClaim.weekend_key == weekend_key,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="You have already claimed this weekend's VIP benefit.")
    claim = WeekendBenefitClaim(
        code=loyalty_code(),
        customer_id=user.id,
        weekend_key=weekend_key,
        reward_name=configuration.weekend_reward_name,
        status="pending",
    )
    db.add(claim)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already claimed this weekend's VIP benefit.") from exc
    return weekend_claim_response(claim)


@app.get("/api/v1/admin/loyalty/settings")
def admin_loyalty_settings(_: str = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    return configuration_response(loyalty_configuration(db))


@app.put("/api/v1/admin/loyalty/settings")
def update_admin_loyalty_settings(
    payload: LoyaltyConfigurationUpdate,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ZoneInfo(payload.timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Choose a valid IANA time zone.") from exc
    configuration = loyalty_configuration(db)
    configuration.standard_min_spend_minor = payload.standard_min_spend_kes * 100
    configuration.standard_award_points = payload.standard_award_points
    configuration.standard_redeem_threshold = payload.standard_redeem_threshold
    configuration.vip_min_spend_minor = payload.vip_min_spend_kes * 100
    configuration.vip_award_points = payload.vip_award_points
    configuration.vip_qualification_points = payload.vip_qualification_points
    configuration.weekend_days = ",".join(payload.weekend_days)
    configuration.weekend_start = payload.weekend_start
    configuration.weekend_end = payload.weekend_end
    configuration.weekend_reward_name = payload.weekend_reward_name.strip()
    configuration.weekend_reward_description = payload.weekend_reward_description.strip()
    configuration.timezone_name = payload.timezone_name
    add_admin_audit_log(
        db,
        admin,
        "loyalty_settings_updated",
        "loyalty_configuration",
        configuration.id,
        reason="Administrator updated loyalty earning, redemption, and VIP benefit rules.",
        details=configuration_response(configuration),
    )
    db.commit()
    return configuration_response(configuration)


@app.get("/api/v1/admin/loyalty/rewards")
def admin_loyalty_rewards(_: str = Depends(current_admin), db: Session = Depends(get_db)) -> list[dict]:
    return [
        reward_response(db, reward)
        for reward in db.scalars(select(Reward).order_by(Reward.points_cost, Reward.name))
    ]


@app.post("/api/v1/admin/loyalty/rewards", status_code=201)
def create_admin_loyalty_reward(
    payload: RewardWriteRequest,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    if payload.menu_item_id and db.get(MenuItem, payload.menu_item_id) is None:
        raise HTTPException(status_code=422, detail="Choose an existing menu item.")
    reward = Reward(
        menu_item_id=payload.menu_item_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        points_cost=payload.points_cost,
        conditions=payload.conditions.strip(),
        available=payload.available,
    )
    db.add(reward)
    db.flush()
    add_admin_audit_log(db, admin, "reward_created", "reward", reward.id, details=reward_response(db, reward))
    db.commit()
    return reward_response(db, reward)


@app.put("/api/v1/admin/loyalty/rewards/{reward_id}")
def update_admin_loyalty_reward(
    reward_id: str,
    payload: RewardWriteRequest,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward not found.")
    if payload.menu_item_id and db.get(MenuItem, payload.menu_item_id) is None:
        raise HTTPException(status_code=422, detail="Choose an existing menu item.")
    reward.menu_item_id = payload.menu_item_id
    reward.name = payload.name.strip()
    reward.description = payload.description.strip()
    reward.points_cost = payload.points_cost
    reward.conditions = payload.conditions.strip()
    reward.available = payload.available
    add_admin_audit_log(db, admin, "reward_updated", "reward", reward.id, details=reward_response(db, reward))
    db.commit()
    return reward_response(db, reward)


@app.delete("/api/v1/admin/loyalty/rewards/{reward_id}", status_code=204)
def hide_admin_loyalty_reward(
    reward_id: str,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> None:
    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward not found.")
    reward.available = False
    add_admin_audit_log(db, admin, "reward_hidden", "reward", reward.id, reason="Removed from customer reward catalogue.")
    db.commit()


@app.get("/api/v1/admin/loyalty/members")
def admin_loyalty_members(
    search: str = "",
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(User).outerjoin(LoyaltyProfile, LoyaltyProfile.customer_id == User.id)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
                LoyaltyProfile.vip_membership_number.ilike(term),
            )
        )
    users = list(db.scalars(query.order_by(User.created_at.desc())).unique())
    return [
        {
            "customer_id": member.id,
            "name": member.name,
            "email": member.email,
            "phone": member.phone,
            "delivery_address": member.delivery_address,
            "created_at": member.created_at,
            "standard_balance": ledger_points(db, member.id, "standard"),
            "standard_earned": ledger_points(db, member.id, "standard", "earned"),
            "vip_balance": ledger_points(db, member.id, "vip"),
            "vip_earned": ledger_points(db, member.id, "vip", "earned"),
            "vip_membership_number": member.loyalty_profile.vip_membership_number if member.loyalty_profile else None,
            "vip_status": (
                "Suspended" if member.loyalty_profile and member.loyalty_profile.suspended_at
                else "Active" if member.loyalty_profile and member.loyalty_profile.vip_qualified_at
                else "Not Yet Qualified"
            ),
        }
        for member in users
    ]


@app.get("/api/v1/admin/loyalty/redemptions")
def admin_loyalty_redemptions(_: str = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    redemptions = list(
        db.scalars(select(RewardRedemption).order_by(RewardRedemption.created_at.desc()).limit(200))
    )
    claims = list(
        db.scalars(select(WeekendBenefitClaim).order_by(WeekendBenefitClaim.created_at.desc()).limit(200))
    )
    return {
        "rewards": [
            {**redemption_response(db, redemption), "customer_id": redemption.customer_id}
            for redemption in redemptions
        ],
        "vip_weekends": [
            {**weekend_claim_response(claim), "customer_id": claim.customer_id}
            for claim in claims
        ],
    }


@app.get("/api/v1/admin/loyalty/analytics")
def admin_loyalty_analytics(_: str = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    return {
        "members": int(db.scalar(select(func.count(User.id))) or 0),
        "active_vip_members": int(
            db.scalar(
                select(func.count(LoyaltyProfile.customer_id)).where(
                    LoyaltyProfile.vip_qualified_at.is_not(None),
                    LoyaltyProfile.suspended_at.is_(None),
                )
            )
            or 0
        ),
        "standard_points_outstanding": int(
            db.scalar(
                select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(
                    LoyaltyTransaction.track == "standard"
                )
            )
            or 0
        ),
        "vip_points_issued": int(
            db.scalar(
                select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(
                    LoyaltyTransaction.track == "vip",
                    LoyaltyTransaction.transaction_type == "earned",
                )
            )
            or 0
        ),
        "pending_reward_redemptions": int(
            db.scalar(
                select(func.count(RewardRedemption.id)).where(RewardRedemption.status == "pending")
            )
            or 0
        ),
        "pending_vip_claims": int(
            db.scalar(
                select(func.count(WeekendBenefitClaim.id)).where(WeekendBenefitClaim.status == "pending")
            )
            or 0
        ),
    }


@app.get("/api/v1/admin/loyalty/export")
def export_loyalty_report(_: str = Depends(current_admin), db: Session = Depends(get_db)) -> Response:
    def safe_csv(value: object) -> str:
        text = "" if value is None else str(value)
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "customer_id",
            "name",
            "email",
            "phone",
            "standard_balance",
            "standard_lifetime_earned",
            "vip_balance",
            "vip_lifetime_earned",
            "vip_membership_number",
            "vip_status",
        ]
    )
    users = list(db.scalars(select(User).options(joinedload(User.loyalty_profile)).order_by(User.created_at)))
    for member in users:
        profile = member.loyalty_profile
        writer.writerow(
            safe_csv(value)
            for value in (
                member.id,
                member.name,
                member.email,
                member.phone,
                ledger_points(db, member.id, "standard"),
                ledger_points(db, member.id, "standard", "earned"),
                ledger_points(db, member.id, "vip"),
                ledger_points(db, member.id, "vip", "earned"),
                profile.vip_membership_number if profile else None,
                "Suspended" if profile and profile.suspended_at else "Active" if profile and profile.vip_qualified_at else "Not Yet Qualified",
            )
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="merryland-loyalty-members.csv"'},
    )


@app.get("/api/v1/admin/loyalty/members/{customer_id}/activity")
def admin_loyalty_member_activity(
    customer_id: str,
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    member = db.get(User, customer_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    entries = list(
        db.scalars(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.customer_id == customer_id)
            .order_by(LoyaltyTransaction.created_at.desc())
            .limit(200)
        )
    )
    orders = list(
        db.scalars(
            select(Order)
            .join(Payment)
            .options(joinedload(Order.payment), selectinload(Order.items))
            .where(Order.customer_id == customer_id, Payment.status == "succeeded")
            .order_by(Order.created_at.desc())
            .limit(100)
        ).unique()
    )
    return {
        "transactions": [
            {
                "track": entry.track,
                "type": entry.transaction_type,
                "points": entry.points,
                "description": entry.description,
                "reason": entry.reason,
                "admin_actor": entry.admin_actor,
                "created_at": entry.created_at,
            }
            for entry in entries
        ],
        "orders": [
            {
                "order_number": order.order_number,
                "total_minor": order.total_minor,
                "status": order.status,
                "created_at": order.created_at,
                "items": [
                    {"name": item.item_name, "quantity": item.quantity, "eligible": item.points_eligible}
                    for item in order.items
                ],
                "awards": [
                    {
                        "track": entry.track,
                        "points": entry.points,
                    }
                    for entry in entries
                    if entry.order_id == order.id and entry.transaction_type == "earned"
                ],
            }
            for order in orders
        ],
    }


@app.get("/api/v1/admin/loyalty/audit-logs")
def admin_loyalty_audit_logs(
    _: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": entry.id,
            "admin_actor": entry.admin_actor,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "reason": entry.reason,
            "details": json.loads(entry.details),
            "created_at": entry.created_at,
        }
        for entry in db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(500))
    ]


@app.post("/api/v1/admin/loyalty/verify")
def verify_loyalty_code(
    payload: LoyaltyVerifyRequest,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    code = payload.code.strip().upper()
    redemption = db.scalar(select(RewardRedemption).where(RewardRedemption.code == code).with_for_update())
    if redemption is not None:
        if redemption.status != "pending":
            raise HTTPException(status_code=409, detail=f"This reward code is already {redemption.status}.")
        db.scalar(select(User.id).where(User.id == redemption.customer_id).with_for_update())
        profile = ensure_loyalty_profile(db, redemption.customer_id, lock=True)
        if profile.suspended_at is not None:
            raise HTTPException(status_code=403, detail="The customer's loyalty account is suspended.")
        if available_standard_points(db, redemption.customer_id, exclude_redemption_id=redemption.id) < redemption.points_cost:
            raise HTTPException(status_code=409, detail="The customer no longer has enough points to confirm this reward.")
        redemption.status = "redeemed"
        redemption.redeemed_at = datetime.now(timezone.utc)
        redemption.redeemed_by = admin
        db.add(
            LoyaltyTransaction(
                customer_id=redemption.customer_id,
                idempotency_key=f"reward-redemption:{redemption.id}",
                transaction_type="redeemed",
                track="standard",
                points=-redemption.points_cost,
                description=f"Redeemed {redemption_response(db, redemption)['reward_name']}",
            )
        )
        add_admin_audit_log(
            db,
            admin,
            "reward_redeemed",
            "reward_redemption",
            redemption.id,
            reason=f"Reward redemption verified using code {code}.",
            details={"customer_id": redemption.customer_id, "points": redemption.points_cost},
        )
        db.commit()
        return {"type": "reward", **redemption_response(db, redemption)}
    claim = db.scalar(select(WeekendBenefitClaim).where(WeekendBenefitClaim.code == code).with_for_update())
    if claim is None:
        profile = db.scalar(
            select(LoyaltyProfile).where(LoyaltyProfile.vip_membership_number == code)
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="Redemption or VIP membership code not found.")
        if profile.vip_qualified_at is None or profile.suspended_at is not None:
            raise HTTPException(status_code=403, detail="This VIP membership is not active.")
        customer = db.get(User, profile.customer_id)
        return {
            "type": "vip_card",
            "customer_id": profile.customer_id,
            "customer_name": customer.name if customer else "",
            "membership_number": profile.vip_membership_number,
            "status": "Active",
        }
    if claim.status != "pending":
        raise HTTPException(status_code=409, detail=f"This VIP benefit code is already {claim.status}.")
    configuration = loyalty_configuration(db)
    local_now = datetime.now(ZoneInfo(configuration.timezone_name))
    current_weekend_key = local_now.date() - timedelta(days=local_now.weekday())
    if (
        claim.weekend_key != current_weekend_key
        or local_now.strftime("%A") not in configuration.weekend_days.split(",")
        or not configuration.weekend_start <= local_now.time().replace(tzinfo=None) <= configuration.weekend_end
    ):
        claim.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="This VIP weekend benefit has expired.")
    claim.status = "redeemed"
    claim.redeemed_at = datetime.now(timezone.utc)
    claim.redeemed_by = admin
    add_admin_audit_log(
        db,
        admin,
        "vip_weekend_benefit_redeemed",
        "weekend_benefit_claim",
        claim.id,
        reason=f"VIP weekend benefit verified using code {code}.",
        details={"customer_id": claim.customer_id, "weekend_key": claim.weekend_key.isoformat()},
    )
    db.commit()
    return {"type": "vip_weekend", **weekend_claim_response(claim)}


@app.post("/api/v1/admin/loyalty/members/{customer_id}/adjustments", status_code=201)
def adjust_loyalty_points(
    customer_id: str,
    payload: LoyaltyAdjustmentRequest,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    customer = db.scalar(select(User).where(User.id == customer_id).with_for_update())
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    ensure_loyalty_profile(db, customer_id, lock=True)
    if payload.track == "standard" and available_standard_points(db, customer_id) + payload.points < 0:
        raise HTTPException(status_code=409, detail="The adjustment cannot reduce available standard points below zero.")
    if payload.track == "vip" and ledger_points(db, customer_id, "vip") + payload.points < 0:
        raise HTTPException(status_code=409, detail="The adjustment cannot reduce VIP points below zero.")
    transaction = LoyaltyTransaction(
        customer_id=customer_id,
        idempotency_key=f"admin-adjustment:{uuid4()}",
        transaction_type="adjustment",
        track=payload.track,
        points=payload.points,
        description=f"Administrator {payload.track} points adjustment",
        admin_actor=admin,
        reason=payload.reason.strip(),
    )
    db.add(transaction)
    db.flush()
    add_admin_audit_log(
        db,
        admin,
        "points_adjusted",
        "loyalty_transaction",
        transaction.id,
        reason=payload.reason.strip(),
        details={"customer_id": customer_id, "track": payload.track, "points": payload.points},
    )
    db.commit()
    return {
        "id": transaction.id,
        "track": transaction.track,
        "points": transaction.points,
        "admin_actor": transaction.admin_actor,
        "reason": transaction.reason,
        "created_at": transaction.created_at,
    }


@app.patch("/api/v1/admin/loyalty/members/{customer_id}/suspension")
def update_loyalty_suspension(
    customer_id: str,
    payload: LoyaltySuspensionUpdate,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(User, customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    profile = ensure_loyalty_profile(db, customer_id, lock=True)
    if payload.suspended:
        profile.suspended_at = datetime.now(timezone.utc)
        profile.suspension_reason = payload.reason.strip()
    else:
        profile.suspended_at = None
        profile.suspension_reason = None
    db.add(
        LoyaltyTransaction(
            customer_id=customer_id,
            idempotency_key=f"admin-suspension:{uuid4()}",
            transaction_type="audit",
            track="standard",
            points=0,
            description="Loyalty account suspended" if payload.suspended else "Loyalty account reinstated",
            admin_actor=admin,
            reason=payload.reason.strip() or "Reinstated by administrator",
        )
    )
    add_admin_audit_log(
        db,
        admin,
        "loyalty_account_suspended" if payload.suspended else "loyalty_account_reinstated",
        "loyalty_profile",
        customer_id,
        reason=payload.reason.strip() or "Reinstated by administrator.",
    )
    db.commit()
    return {
        "customer_id": customer_id,
        "suspended": payload.suspended,
        "suspension_reason": profile.suspension_reason,
    }
