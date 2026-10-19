import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-local-tests"

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.api import routes as main_module
from app.main import app
from app.db.models import (
    Category,
    LoyaltyConfiguration,
    LoyaltyTransaction,
    MenuItem,
)


def test_google_auth_creates_account_and_links_verified_email(monkeypatch):
    claims = {
        "sub": "google-subject-123",
        "email": "google-customer@example.test",
        "email_verified": True,
        "name": "Google Customer",
        "aud": "test-google-client",
    }
    monkeypatch.setattr(main_module.settings, "google_client_ids", "test-google-client")
    monkeypatch.setattr(main_module, "verify_google_id_token", lambda token, allowed: claims)

    with TestClient(app) as client:
        created = client.post("/api/v1/auth/google", json={"id_token": "verified-test-token"})
        assert created.status_code == 200
        created_user = created.json()["user"]
        assert created_user["email"] == claims["email"]
        assert created_user["phone"] is None
        headers = {"Authorization": f"Bearer {created.json()['access_token']}"}
        assert client.get(
            "/api/v1/auth/me",
            headers=headers,
        ).json()["id"] == created_user["id"]

        existing = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Existing Customer",
                "email": "link-customer@example.test",
                "phone": "+254700333444",
                "password": "a-long-test-password",
            },
        )
        claims.update(
            sub="google-subject-link",
            email="LINK-CUSTOMER@example.test",
            name="Google Profile Name",
        )
        linked = client.post("/api/v1/auth/google", json={"id_token": "verified-test-token"})
        assert linked.status_code == 200
        assert linked.json()["user"]["id"] == existing.json()["user"]["id"]


def test_google_auth_rejects_unverified_email(monkeypatch):
    monkeypatch.setattr(main_module.settings, "google_client_ids", "test-google-client")
    monkeypatch.setattr(
        main_module,
        "verify_google_id_token",
        lambda token, allowed: {
            "sub": "unverified-subject",
            "email": "unverified@example.test",
            "email_verified": False,
            "aud": "test-google-client",
        },
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/google", json={"id_token": "unverified-token"})
        assert response.status_code == 401


def test_customer_can_manage_profile_and_photo():
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Profile Customer",
                "email": "profile-customer@example.test",
                "phone": "+254700555401",
                "password": "a-long-test-password",
            },
        )
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        profile = client.get("/api/v1/auth/me", headers=headers)
        assert profile.status_code == 200
        assert profile.json()["email"] == "profile-customer@example.test"
        assert profile.json()["delivery_address"] is None

        updated = client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={
                "name": "  Profile Customer Updated  ",
                "phone": "",
                "delivery_address": "  15 Garden Road, Nairobi  ",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Profile Customer Updated"
        assert updated.json()["phone"] is None
        assert updated.json()["delivery_address"] == "15 Garden Road, Nairobi"
        assert updated.json()["email"] == "profile-customer@example.test"

        photo = client.post(
            "/api/v1/auth/me/photo",
            headers=headers,
            files={"image": ("profile.png", b"\x89PNG\r\n\x1a\nprofile-image", "image/png")},
        )
        assert photo.status_code == 200
        photo_url = photo.json()["profile_image_url"]
        assert photo_url.endswith(".png")

        rejected_photo = client.post(
            "/api/v1/auth/me/photo",
            headers=headers,
            files={"image": ("profile.svg", b"<svg/>", "image/svg+xml")},
        )
        assert rejected_photo.status_code == 415

        removed_photo = client.delete("/api/v1/auth/me/photo", headers=headers)
        assert removed_photo.status_code == 204
        assert client.get("/api/v1/auth/me", headers=headers).json()["profile_image_url"] is None
        assert client.patch("/api/v1/auth/me", json={"name": "Unauthenticated"}).status_code == 401


def test_customer_order_payment_and_loyalty_are_connected(monkeypatch):
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me").status_code == 401
        invalid_registration = client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": "not-an-email", "phone": "+254700555111", "password": "long-password"},
        )
        assert invalid_registration.status_code == 422

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Test Customer",
                "email": "customer@example.test",
                "phone": "+254700123456",
                "password": "a-long-test-password",
            },
        )
        assert registered.status_code == 201
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        monkeypatch_admin = {"username": "Beatrice", "password": "a-separate-admin-password"}
        monkeypatch.setattr(main_module.settings, "admin_username", monkeypatch_admin["username"])
        monkeypatch.setattr(main_module.settings, "admin_password", monkeypatch_admin["password"])
        admin_login = client.post("/api/v1/admin/auth/login", json=monkeypatch_admin)
        assert admin_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        members = client.get("/api/v1/admin/loyalty/members", headers=admin_headers)
        assert members.status_code == 200
        registered_member = next(
            member for member in members.json()
            if member["customer_id"] == registered.json()["user"]["id"]
        )
        assert registered_member["name"] == "Test Customer"
        assert registered_member["email"] == "customer@example.test"
        assert registered_member["phone"] == "+254700123456"
        assert registered_member["created_at"]

        posted = client.post(
            "/api/v1/admin/menu",
            headers=admin_headers,
            json={
                "category_name": "Food",
                "name": "Test checkout meal",
                "description": "A menu item created by the admin.",
                "price_minor": 85000,
                "marked_price_minor": 100000,
                "image_url": "https://example.test/meal.jpg",
                "prep_minutes": 20,
                "available": True,
            },
        )
        assert posted.status_code == 201
        assert client.get("/api/v1/admin/menu", headers=headers).status_code == 403

        menu = client.get("/api/v1/menu")
        assert menu.status_code == 200
        item = next(entry for entry in menu.json() if entry["id"] == posted.json()["id"])
        assert item["category_name"] == "Food"
        assert item["marked_price_minor"] == 100000

        order_response = client.post(
            "/api/v1/orders",
            headers=headers,
            json={"order_type": "takeaway", "items": [{"menu_item_id": item["id"], "quantity": 1}]},
        )
        assert order_response.status_code == 201
        order = order_response.json()
        assert order["status"] == "pending_payment"
        assert order["payment"]["status"] == "pending"
        assert order["total_minor"] == item["price_minor"]

        with SessionLocal() as db:
            product = db.get(MenuItem, item["id"])
            product.price_minor = item["price_minor"] * 2
            product.points_eligible = False
            db.commit()

        payment_url = f"/api/v1/payments/{order['payment']['id']}/simulate-success"
        confirmed = client.post(payment_url, headers=headers)
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"

        repeated = client.post(payment_url, headers=headers)
        assert repeated.status_code == 200
        balance = client.get("/api/v1/loyalty/balance", headers=headers).json()
        expected_points = 5 if item["price_minor"] > 20_000 else 0
        assert balance["balance"] == expected_points
        assert len(balance["transactions"]) == (1 if expected_points else 0)


def test_admin_menu_upload_customer_ratings_and_soft_delete(monkeypatch):
    monkeypatch.setattr(main_module.settings, "admin_username", "Beatrice")
    monkeypatch.setattr(main_module.settings, "admin_password", "a-separate-admin-password")

    with TestClient(app) as client:
        assert client.get("/api/v1/admin/menu").status_code == 401
        invalid_login = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "Beatrice", "password": "incorrect-password"},
        )
        assert invalid_login.status_code == 401
        login = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "BEATRICE", "password": "a-separate-admin-password"},
        )
        assert login.status_code == 200
        legacy_login = client.post(
            "/api/v1/admin/auth/login",
            json={"email": "Beatrice", "password": "a-separate-admin-password"},
        )
        assert legacy_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        uploaded = client.post(
            "/api/v1/admin/menu/images",
            headers=admin_headers,
            files={"image": ("sample.png", b"\x89PNG\r\n\x1a\nminimal image data", "image/png")},
        )
        assert uploaded.status_code == 201
        image_url = uploaded.json()["image_url"]
        filename = image_url.rsplit("/", maxsplit=1)[-1]
        image_path = main_module.UPLOAD_DIR / filename
        try:
            assert client.get(f"/uploads/{filename}").content.startswith(b"\x89PNG")
            invalid_image = client.post(
                "/api/v1/admin/menu/images",
                headers=admin_headers,
                files={"image": ("not-image.png", b"not an image", "image/png")},
            )
            assert invalid_image.status_code == 415

            invalid_price = client.post(
                "/api/v1/admin/menu",
                headers=admin_headers,
                json={
                    "category_name": "Bites",
                    "name": "Discounted snack",
                    "description": "A test snack.",
                    "price_minor": 30000,
                    "marked_price_minor": 25000,
                    "image_url": image_url,
                },
            )
            assert invalid_price.status_code == 422

            posted = client.post(
                "/api/v1/admin/menu",
                headers=admin_headers,
                json={
                    "category_name": "Bites",
                    "name": "Discounted snack",
                    "description": "A test snack.",
                    "price_minor": 30000,
                    "marked_price_minor": 45000,
                    "image_url": image_url,
                },
            )
            assert posted.status_code == 201
            product_id = posted.json()["id"]

            customer = client.post(
                "/api/v1/auth/register",
                json={
                    "name": "Rating Customer",
                    "email": "rating-customer@example.test",
                    "phone": "+254700888999",
                    "password": "a-long-test-password",
                },
            )
            customer_headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}
            assert client.post(
                f"/api/v1/menu/{product_id}/ratings",
                headers=customer_headers,
                json={"rating": 5},
            ).json() == {"rating_average": 5.0, "rating_count": 1, "your_rating": 5}
            updated_rating = client.post(
                f"/api/v1/menu/{product_id}/ratings",
                headers=customer_headers,
                json={"rating": 3},
            )
            assert updated_rating.json() == {"rating_average": 3.0, "rating_count": 1, "your_rating": 3}

            second_customer = client.post(
                "/api/v1/auth/register",
                json={
                    "name": "Second Rating Customer",
                    "email": "second-rating-customer@example.test",
                    "phone": "+254700888998",
                    "password": "a-long-test-password",
                },
            )
            second_headers = {"Authorization": f"Bearer {second_customer.json()['access_token']}"}
            averaged = client.post(
                f"/api/v1/menu/{product_id}/ratings",
                headers=second_headers,
                json={"rating": 4},
            )
            assert averaged.json() == {"rating_average": 3.5, "rating_count": 2, "your_rating": 4}
            public_item = next(
                item for item in client.get("/api/v1/menu").json()
                if item["id"] == product_id
            )
            assert public_item["rating_average"] == 3.5
            assert public_item["rating_count"] == 2

            updated = client.put(
                f"/api/v1/admin/menu/{product_id}",
                headers=admin_headers,
                json={
                    "category_name": "Drinks",
                    "name": "Updated discounted drink",
                    "description": "The product was edited.",
                    "price_minor": 32000,
                    "marked_price_minor": 45000,
                    "image_url": image_url,
                    "prep_minutes": 5,
                    "available": True,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["category_name"] == "Drinks"
            assert updated.json()["price_minor"] == 32000

            assert client.delete(f"/api/v1/admin/menu/{product_id}", headers=admin_headers).status_code == 204
            assert product_id not in {item["id"] for item in client.get("/api/v1/menu").json()}
            hidden = next(
                item for item in client.get("/api/v1/admin/menu", headers=admin_headers).json()
                if item["id"] == product_id
            )
            assert hidden["available"] is False
        finally:
            image_path.unlink(missing_ok=True)


def test_standard_and_vip_points_use_strict_order_thresholds_and_are_idempotent(monkeypatch):
    monkeypatch.setattr(main_module.settings, "admin_username", "Beatrice")
    monkeypatch.setattr(main_module.settings, "admin_password", "a-separate-admin-password")
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Threshold Customer",
                "email": "threshold-customer@example.test",
                "phone": "+254700111222",
                "password": "a-long-test-password",
            },
        )
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        with SessionLocal() as db:
            configuration = db.get(LoyaltyConfiguration, "default")
            configuration.standard_min_spend_minor = 20_000
            configuration.standard_award_points = 5
            configuration.vip_min_spend_minor = 100_000
            configuration.vip_award_points = 10
            configuration.vip_qualification_points = 100
            category = db.query(Category).filter_by(name="Food").one()
            items = [
                MenuItem(category_id=category.id, name="Exactly KSh 200", price_minor=20_000, available=True),
                MenuItem(category_id=category.id, name="KSh 250 order", price_minor=25_000, available=True),
                MenuItem(category_id=category.id, name="KSh 1200 order", price_minor=120_000, available=True),
            ]
            db.add_all(items)
            db.commit()
            item_ids = [item.id for item in items]

        expected = [(0, 0), (5, 0), (5, 10)]
        payment_urls = []
        order_ids = []
        for item_id, (standard_points, vip_points) in zip(item_ids, expected):
            order = client.post(
                "/api/v1/orders",
                headers=headers,
                json={"order_type": "takeaway", "items": [{"menu_item_id": item_id, "quantity": 1}]},
            )
            assert order.status_code == 201
            order_ids.append(order.json()["id"])
            payment_url = f"/api/v1/payments/{order.json()['payment']['id']}/simulate-success"
            payment_urls.append(payment_url)
            assert client.post(payment_url, headers=headers).status_code == 200
            balance = client.get("/api/v1/loyalty/balance", headers=headers).json()
            assert balance["balance"] == sum(points[0] for points in expected[: len(payment_urls)])
            assert balance["vip_balance"] == sum(points[1] for points in expected[: len(payment_urls)])

        assert client.post(payment_urls[-1], headers=headers).status_code == 200
        final_balance = client.get("/api/v1/loyalty/balance", headers=headers).json()
        assert final_balance["balance"] == 10
        assert final_balance["vip_balance"] == 10
        dashboard = client.get("/api/v1/loyalty/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["vip"]["status"] == "Not Yet Qualified"
        points_by_order = {order["id"]: (order["standard_points"], order["vip_points"]) for order in dashboard.json()["orders"]}
        assert [points_by_order[order_id] for order_id in order_ids] == expected

        with SessionLocal() as db:
            db.add_all(
                LoyaltyTransaction(
                    customer_id=registered.json()["user"]["id"],
                    idempotency_key=f"test-unrelated-audit-{index}",
                    transaction_type="audit",
                    track="standard",
                    points=0,
                    description="Unrelated account audit entry",
                )
                for index in range(110)
            )
            db.commit()

        dashboard_after_history_grows = client.get("/api/v1/loyalty/dashboard", headers=headers)
        assert dashboard_after_history_grows.status_code == 200
        points_after_history_grows = {
            order["id"]: (order["standard_points"], order["vip_points"])
            for order in dashboard_after_history_grows.json()["orders"]
        }
        assert [points_after_history_grows[order_id] for order_id in order_ids] == expected


def test_redemptions_reserve_points_until_staff_verifies_once(monkeypatch):
    monkeypatch.setattr(main_module.settings, "admin_username", "Beatrice")
    monkeypatch.setattr(main_module.settings, "admin_password", "a-separate-admin-password")
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Reward Customer",
                "email": "reward-customer@example.test",
                "phone": "+254700111223",
                "password": "a-long-test-password",
            },
        )
        customer_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        admin_login = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "Beatrice", "password": "a-separate-admin-password"},
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        with SessionLocal() as db:
            db.add(
                LoyaltyTransaction(
                    customer_id=registered.json()["user"]["id"],
                    idempotency_key="test-earned-reward-points",
                    transaction_type="earned",
                    track="standard",
                    points=200,
                    description="Test reward balance",
                )
            )
            db.commit()
        reward = client.post(
            "/api/v1/admin/loyalty/rewards",
            headers=admin_headers,
            json={"name": "Free side", "description": "A test reward.", "points_cost": 100},
        )
        assert reward.status_code == 201
        assert client.get("/api/v1/admin/loyalty/settings").status_code == 401
        claim = client.post(
            f"/api/v1/loyalty/rewards/{reward.json()['id']}/redeem",
            headers=customer_headers,
        )
        assert claim.status_code == 201
        assert client.get("/api/v1/loyalty/dashboard", headers=customer_headers).json()["standard"]["balance"] == 100
        verified = client.post(
            "/api/v1/admin/loyalty/verify",
            headers=admin_headers,
            json={"code": claim.json()["code"]},
        )
        assert verified.status_code == 200
        assert verified.json()["status"] == "redeemed"
        assert client.post(
            "/api/v1/admin/loyalty/verify",
            headers=admin_headers,
            json={"code": claim.json()["code"]},
        ).status_code == 409
        balance = client.get("/api/v1/loyalty/balance", headers=customer_headers).json()
        assert balance["balance"] == 100
        assert sum(entry["points"] for entry in balance["transactions"]) == 100


def test_vip_membership_weekend_benefit_and_admin_adjustment_audit(monkeypatch):
    monkeypatch.setattr(main_module.settings, "admin_username", "Beatrice")
    monkeypatch.setattr(main_module.settings, "admin_password", "a-separate-admin-password")
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "name": "VIP Customer",
                "email": "vip-customer@example.test",
                "phone": "+254700111224",
                "password": "a-long-test-password",
            },
        )
        customer_id = registered.json()["user"]["id"]
        customer_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        admin_login = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "Beatrice", "password": "a-separate-admin-password"},
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        with SessionLocal() as db:
            configuration = db.get(LoyaltyConfiguration, "default")
            configuration.weekend_days = datetime.now(ZoneInfo(configuration.timezone_name)).strftime("%A")
            configuration.weekend_start = time(0, 0)
            configuration.weekend_end = time(23, 59)
            db.add(
                LoyaltyTransaction(
                    customer_id=customer_id,
                    idempotency_key="test-earned-vip-qualification",
                    transaction_type="earned",
                    track="vip",
                    points=100,
                    description="Test VIP qualification",
                )
            )
            db.commit()

        dashboard = client.get("/api/v1/loyalty/dashboard", headers=customer_headers).json()
        assert dashboard["vip"]["status"] == "Active"
        assert dashboard["vip"]["membership_number"].startswith("MR-VIP-")
        claim = client.post("/api/v1/loyalty/vip/weekend/claim", headers=customer_headers)
        assert claim.status_code == 201
        assert client.post("/api/v1/loyalty/vip/weekend/claim", headers=customer_headers).status_code == 409
        verified = client.post(
            "/api/v1/admin/loyalty/verify",
            headers=admin_headers,
            json={"code": claim.json()["code"]},
        )
        assert verified.status_code == 200
        assert verified.json()["type"] == "vip_weekend"
        adjusted = client.post(
            f"/api/v1/admin/loyalty/members/{customer_id}/adjustments",
            headers=admin_headers,
            json={"track": "standard", "points": 5, "reason": "Courtesy point correction"},
        )
        assert adjusted.status_code == 201
        assert adjusted.json()["admin_actor"] == "beatrice"
        assert adjusted.json()["reason"] == "Courtesy point correction"
        members = client.get(
            "/api/v1/admin/loyalty/members",
            headers=admin_headers,
            params={"search": "vip-customer"},
        )
        assert members.status_code == 200
        assert members.json()[0]["customer_id"] == customer_id
        assert members.json()[0]["vip_status"] == "Active"
        activity = client.get(
            f"/api/v1/admin/loyalty/members/{customer_id}/activity",
            headers=admin_headers,
        )
        assert activity.status_code == 200
        assert any(entry["reason"] == "Courtesy point correction" for entry in activity.json()["transactions"])
        assert activity.json()["orders"] == []
        audit_logs = client.get("/api/v1/admin/loyalty/audit-logs", headers=admin_headers)
        assert audit_logs.status_code == 200
        assert any(entry["action"] == "points_adjusted" for entry in audit_logs.json())
        export = client.get("/api/v1/admin/loyalty/export", headers=admin_headers)
        assert export.status_code == 200
        assert export.headers["content-type"].startswith("text/csv")
        assert "vip-customer@example.test" in export.text
        membership = client.post(
            "/api/v1/admin/loyalty/verify",
            headers=admin_headers,
            json={"code": dashboard["vip"]["membership_number"]},
        )
        assert membership.status_code == 200
        assert membership.json()["type"] == "vip_card"
        suspended = client.patch(
            f"/api/v1/admin/loyalty/members/{customer_id}/suspension",
            headers=admin_headers,
            json={"suspended": True, "reason": "Membership review"},
        )
        assert suspended.status_code == 200
        assert client.post(
            "/api/v1/admin/loyalty/verify",
            headers=admin_headers,
            json={"code": dashboard["vip"]["membership_number"]},
        ).status_code == 403
        reinstated = client.patch(
            f"/api/v1/admin/loyalty/members/{customer_id}/suspension",
            headers=admin_headers,
            json={"suspended": False, "reason": ""},
        )
        assert reinstated.status_code == 200
