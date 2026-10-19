"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import GoogleSignInButton from "./GoogleSignInButton";
import { QRCodeSVG } from "qrcode.react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

type MenuItem = {
  id: string;
  category_id: string;
  category_name: string;
  name: string;
  description: string;
  price_minor: number;
  marked_price_minor: number | null;
  image_url: string;
  prep_minutes: number;
  points_eligible: boolean;
  rating_average: number;
  rating_count: number;
};
type User = { id: string; name: string; email: string; phone: string | null; delivery_address: string | null; profile_image_url: string | null; created_at: string };
type Order = { id: string; order_number: string; status: string; payment: { id: string; status: string } };
type CartLine = { item: MenuItem; quantity: number };
type MenuFilter = "all" | "bites" | "drinks" | "food" | "under-500";
type LoyaltyCode = { id: string; code: string; reward_name: string; points_cost?: number; status: string; created_at: string; redeemed_at: string | null };
type LoyaltyDashboard = {
  standard: {
    balance: number;
    lifetime_earned: number;
    redeem_threshold: number;
    progress: number;
    rewards: { id: string; name: string; description: string; points_cost: number; conditions: string; available: boolean; image_url: string }[];
  };
  vip: {
    balance: number;
    lifetime_earned: number;
    qualification_threshold: number;
    progress: number;
    qualified: boolean;
    membership_number: string | null;
    status: string;
    weekend_benefit: {
      name: string;
      description: string;
      days: string[];
      start: string;
      end: string;
      timezone: string;
      claim_available: boolean;
      current_claim: LoyaltyCode | null;
    };
    claims: LoyaltyCode[];
  };
  redemptions: LoyaltyCode[];
  transactions: { id: string; track: string; type: string; points: number; description: string; created_at: string }[];
  orders: { id: string; order_number: string; status: string; total_minor: number; created_at: string; standard_points: number; vip_points: number }[];
};

const formatKes = (minor: number) => (minor / 100).toLocaleString("en-KE");

export default function Home() {
  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [menuUnavailable, setMenuUnavailable] = useState(false);
  const [menuLoading, setMenuLoading] = useState(true);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [showFavorites, setShowFavorites] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [filter, setFilter] = useState<MenuFilter>("all");
  const [search, setSearch] = useState("");
  const [showAuth, setShowAuth] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [orderType, setOrderType] = useState<"takeaway" | "dine_in">("takeaway");
  const [ratingPending, setRatingPending] = useState<string | null>(null);
  const [showRewards, setShowRewards] = useState(false);
  const [loyaltyDashboard, setLoyaltyDashboard] = useState<LoyaltyDashboard | null>(null);
  const [loyaltyBusy, setLoyaltyBusy] = useState(false);
  const [profileDraft, setProfileDraft] = useState({ name: "", phone: "", delivery_address: "" });
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileNotice, setProfileNotice] = useState("");

  const total = useMemo(() => cart.reduce((sum, line) => sum + line.item.price_minor * line.quantity, 0), [cart]);
  const visibleMenu = useMemo(() => {
    return menu.filter((item) => {
      const category = item.category_name.toLowerCase();
      const isDrink = category.includes("drink");
      const matchesFilter = filter === "all"
        || (filter === "bites" && category === "bites")
        || (filter === "drinks" && isDrink)
        || (filter === "food" && !isDrink)
        || (filter === "under-500" && item.price_minor < 50000);
      const matchesSearch = `${item.name} ${item.description}`.toLowerCase().includes(search.toLowerCase());
      return matchesFilter && matchesSearch;
    });
  }, [filter, menu, search]);
  const displayedMenu = useMemo(
    () => showFavorites ? visibleMenu.filter((item) => favorites.includes(item.id)) : visibleMenu,
    [favorites, showFavorites, visibleMenu],
  );

  const loadMenu = useCallback(async () => {
    try {
      const response = await fetch(`${API}/menu`);
      if (!response.ok) throw new Error("The menu could not be loaded.");
      setMenu(await response.json());
      setMenuUnavailable(false);
    } catch (cause) {
      setMenuUnavailable(true);
      if (!(cause instanceof Error)) setError("The menu could not be loaded.");
    } finally {
      setMenuLoading(false);
    }
  }, []);

  useEffect(() => { void loadMenu(); }, [loadMenu]);
  async function request(path: string, options: RequestInit = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ?? "Something went wrong. Please try again.");
    return data;
  }

  async function loadLoyaltyDashboard(accessToken: string) {
    const headers = { Authorization: `Bearer ${accessToken}` };
    const [dashboardResponse, profileResponse] = await Promise.all([
      fetch(`${API}/loyalty/dashboard`, { headers }),
      fetch(`${API}/auth/me`, { headers }),
    ]);
    const [dashboardData, profileData] = await Promise.all([
      dashboardResponse.json().catch(() => ({})),
      profileResponse.json().catch(() => ({})),
    ]);
    if (!dashboardResponse.ok) throw new Error(dashboardData.detail ?? "Your account dashboard could not be loaded.");
    if (!profileResponse.ok) throw new Error(profileData.detail ?? "Your account profile could not be loaded.");
    const profile = profileData as User;
    setUser(profile);
    setProfileDraft({
      name: profile.name,
      phone: profile.phone ?? "",
      delivery_address: profile.delivery_address ?? "",
    });
    setLoyaltyDashboard(dashboardData as LoyaltyDashboard);
  }

  async function showAccountDashboard(accessToken: string) {
    setShowRewards(true);
    setLoyaltyBusy(true);
    setProfileNotice("");
    try {
      await loadLoyaltyDashboard(accessToken);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your account dashboard could not be loaded.");
    } finally {
      setLoyaltyBusy(false);
    }
  }

  async function submitAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    try {
      const result = await request(`/auth/${authMode}`, { method: "POST", body: JSON.stringify(body) });
      setToken(result.access_token);
      setUser(result.user);
      setShowAuth(false);
      setNotice(`Welcome${authMode === "register" ? " to Merryland" : " back"}, ${result.user.name.split(" ")[0]}.`);
      await showAccountDashboard(result.access_token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  async function submitGoogleAuth(idToken: string) {
    setError("");
    setBusy(true);
    try {
      const result = await request("/auth/google", {
        method: "POST",
        body: JSON.stringify({ id_token: idToken }),
      });
      setToken(result.access_token);
      setUser(result.user);
      setShowAuth(false);
      setNotice(`Welcome to Merryland, ${result.user.name.split(" ")[0]}.`);
      await showAccountDashboard(result.access_token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Google sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function checkout() {
    if (!user) {
      setShowAuth(true);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const order: Order = await request("/orders", {
        method: "POST",
        body: JSON.stringify({
          order_type: orderType,
          table_number: orderType === "dine_in" ? "1" : null,
          items: cart.map(({ item, quantity }) => ({ menu_item_id: item.id, quantity })),
        }),
      });
      setNotice(`Order ${order.order_number} created. Processing with the local development payment demo…`);
      const paid: Order = await request(`/payments/${order.payment.id}/simulate-success`, { method: "POST" });
      setCart([]);
      setNotice(`Order ${paid.order_number} confirmed. Demo payment verified.`);
      await showAccountDashboard(token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Checkout failed. Your cart is unchanged.");
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) return;
    setProfileBusy(true);
    setProfileNotice("");
    setError("");
    try {
      const profile = await request("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({
          name: profileDraft.name.trim(),
          phone: profileDraft.phone.trim() || null,
          delivery_address: profileDraft.delivery_address.trim() || null,
        }),
      }) as User;
      setUser(profile);
      setProfileDraft({
        name: profile.name,
        phone: profile.phone ?? "",
        delivery_address: profile.delivery_address ?? "",
      });
      setProfileNotice("Your profile has been updated.");
    } catch (cause) {
      setProfileNotice(cause instanceof Error ? cause.message : "Your profile could not be updated.");
    } finally {
      setProfileBusy(false);
    }
  }

  async function uploadProfilePhoto(file: File | undefined) {
    if (!file || !user) return;
    setProfileBusy(true);
    setProfileNotice("");
    const formData = new FormData();
    formData.append("image", file);
    try {
      const response = await fetch(`${API}/auth/me/photo`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail ?? "Your profile photo could not be uploaded.");
      setUser(data as User);
      setProfileNotice("Your profile photo has been updated.");
    } catch (cause) {
      setProfileNotice(cause instanceof Error ? cause.message : "Your profile photo could not be uploaded.");
    } finally {
      setProfileBusy(false);
    }
  }

  async function removeProfilePhoto() {
    if (!user?.profile_image_url) return;
    setProfileBusy(true);
    setProfileNotice("");
    try {
      const response = await fetch(`${API}/auth/me/photo`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail ?? "Your profile photo could not be removed.");
      }
      setUser({ ...user, profile_image_url: null });
      setProfileNotice("Your profile photo has been removed.");
    } catch (cause) {
      setProfileNotice(cause instanceof Error ? cause.message : "Your profile photo could not be removed.");
    } finally {
      setProfileBusy(false);
    }
  }

  function addToCart(item: MenuItem) {
    if (menuUnavailable) return;
    setCart((current) => {
      const existing = current.find((line) => line.item.id === item.id);
      return existing
        ? current.map((line) => line.item.id === item.id ? { ...line, quantity: line.quantity + 1 } : line)
        : [...current, { item, quantity: 1 }];
    });
    setNotice(`${item.name} added to your order.`);
    setError("");
  }

  async function rateItem(item: MenuItem, rating: number) {
    if (!user) {
      setAuthMode("login");
      setShowAuth(true);
      setNotice("Sign in to rate menu items. Each account can rate an item once.");
      return;
    }
    setRatingPending(item.id);
    setError("");
    try {
      const result = await request(`/menu/${item.id}/ratings`, {
        method: "POST",
        body: JSON.stringify({ rating }),
      });
      setMenu((current) => current.map((entry) => entry.id === item.id
        ? { ...entry, rating_average: result.rating_average, rating_count: result.rating_count }
        : entry));
      setNotice("Thanks! Your rating has been saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your rating could not be saved.");
    } finally {
      setRatingPending(null);
    }
  }

  function toggleFavorite(item: MenuItem) {
    setFavorites((current) => current.includes(item.id)
      ? current.filter((id) => id !== item.id)
      : [...current, item.id]);
  }

  function scrollToOrder() {
    document.getElementById("order-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function openRewards() {
    if (!user) {
      setAuthMode("login");
      setShowAuth(true);
      return;
    }
    setShowRewards(true);
    setLoyaltyBusy(true);
    setError("");
    try {
      await loadLoyaltyDashboard(token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your rewards could not be loaded.");
    } finally {
      setLoyaltyBusy(false);
    }
  }

  function signOut() {
    setToken("");
    setUser(null);
    setLoyaltyDashboard(null);
    setProfileDraft({ name: "", phone: "", delivery_address: "" });
    setProfileNotice("");
    setShowRewards(false);
    setError("");
    setNotice("You have been signed out.");
  }

  async function redeemLoyaltyReward(rewardId: string) {
    setLoyaltyBusy(true);
    setError("");
    try {
      await request(`/loyalty/rewards/${rewardId}/redeem`, { method: "POST" });
      setLoyaltyDashboard(await request("/loyalty/dashboard") as LoyaltyDashboard);
      setNotice("Your reward is reserved. Show its code to staff to confirm collection.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The reward could not be reserved.");
    } finally {
      setLoyaltyBusy(false);
    }
  }

  async function claimWeekendBenefit() {
    setLoyaltyBusy(true);
    setError("");
    try {
      await request("/loyalty/vip/weekend/claim", { method: "POST" });
      setLoyaltyDashboard(await request("/loyalty/dashboard") as LoyaltyDashboard);
      setNotice("Your VIP nyama choma is reserved. Show its QR code to staff.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The VIP weekend benefit could not be claimed.");
    } finally {
      setLoyaltyBusy(false);
    }
  }

  async function cancelLoyaltyRedemption(redemptionId: string) {
    setLoyaltyBusy(true);
    setError("");
    try {
      await request(`/loyalty/redemptions/${redemptionId}/cancel`, { method: "POST" });
      setLoyaltyDashboard(await request("/loyalty/dashboard") as LoyaltyDashboard);
      setNotice("Reward reservation cancelled; your points are available again.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The reward reservation could not be cancelled.");
    } finally {
      setLoyaltyBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#menu" aria-label="Merryland menu">
          <span className="brand-mark" aria-hidden="true">M</span>
          <span>Merryland<small>Kitchen &amp; Bar</small></span>
        </a>
        <div className="topbar-tools">
          <label className="search-box">
            <span aria-hidden="true">⌕</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the menu" aria-label="Search menu" />
          </label>
          <button className="filter-toggle" onClick={() => setShowFilters((current) => !current)} aria-label={showFilters ? "Hide menu filters" : "Show menu filters"} aria-expanded={showFilters}>
            <span aria-hidden="true">☷</span>
          </button>
          {!user ? (
            <div className="account-actions" aria-label="Account">
              <button className="sign-in-button" onClick={() => { setAuthMode("login"); setShowAuth(true); }}>Sign in</button>
              <button className="create-account-button" onClick={() => { setAuthMode("register"); setShowAuth(true); }}>Create account</button>
            </div>
          ) : (
            <button className="user-greeting" onClick={() => void openRewards()}>Hi, {user.name.split(" ")[0]} · My account &amp; points</button>
          )}
          <button className="order-shortcut" onClick={scrollToOrder}>
            <span className="bag-icon" aria-hidden="true">▱</span>
            <span>Your order</span>
            <span className="cart-count">{cart.reduce((count, line) => count + line.quantity, 0)}</span>
          </button>
        </div>
        <button className="mobile-profile" onClick={() => user ? void openRewards() : (setAuthMode("register"), setShowAuth(true))} aria-label={user ? `Open rewards for ${user.name}` : "Create an account"}>
          {user ? user.name.slice(0, 1).toUpperCase() : "♙"}
        </button>
      </header>
      <div className="app-layout">
        <section id="menu" className="menu-workspace">
          <div className="restaurant-hero">
            <video
              src="/hero-camera-glow.mp4"
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              aria-label="Merryland Choma Zone — great food, great moments"
            />
          </div>
          <div className="menu-titlebar">
            <div className="promotion-copy">
              <span className="eyebrow">A TREAT FROM MERRYLAND</span>
              <h1 aria-label="Claim your free drinks and nyama choma on us.">
                {["Claim", "your", "free", "drinks", "and", "nyama", "choma", "on", "us."].map((word, index) => (
                  <span className={`headline-word${[2, 3, 5, 6].includes(index) ? " headline-word-highlight" : ""}`} key={word}>{word}</span>
                ))}
              </h1>
              <p>Come enjoy complimentary drinks and freshly made nyama choma at Merryland.</p>
            </div>
            <span className={`open-status${menuUnavailable ? " preview-status" : ""}`}><i /> {menuLoading ? "Loading menu" : menuUnavailable ? "Preview menu" : "Menu available"}</span>
          </div>
          <div className="menu-controls">
            {showFilters && <div className="filter-tabs" role="group" aria-label="Filter menu">
              {([
                ["all", "All"],
                ["bites", "Bites"],
                ["drinks", "Drinks"],
                ["food", "Food"],
                ["under-500", "Under KSh 500"],
              ] as const).map(([value, label]) => (
                <button key={value} className={`filter-tab${filter === value ? " active" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>
              ))}
            </div>}
            <button className={`favorites-filter${showFavorites ? " active" : ""}`} aria-pressed={showFavorites} onClick={() => setShowFavorites((current) => !current)} aria-label={showFavorites ? "Show all dishes" : "Show favorites"}>♥</button>
            <span className="item-count">{displayedMenu.length} items</span>
          </div>
          {menuUnavailable && <div className="offline-banner" role="status"><strong>Menu unavailable</strong><span>We could not connect to the live menu. Please try again soon.</span></div>}
          {(notice || error) && <div className={`notice${error ? " error" : ""}`} role="status">{error || notice}</div>}
          <div className="menu-grid">
            {displayedMenu.map((item) => (
              <article className="menu-card" key={item.id}>
                <div className="menu-photo">
                  {item.image_url && <img className="menu-product-image" src={item.image_url} alt={item.name} loading="lazy" decoding="async" />}
                  {!item.image_url && <span className="image-placeholder" aria-hidden="true">M</span>}
                  <span className="prep-badge"><span aria-hidden="true">◷</span> {item.prep_minutes} min</span>
                  {cart.some((line) => line.item.id === item.id) && !menuUnavailable && <span className="added-badge">In your order</span>}
                  {item.points_eligible && <span className="rewards-badge" title="Points are earned on eligible paid orders and can be redeemed for available food and drink rewards.">Points toward free choma &amp; drinks</span>}
                  <button className={`favorite-button${favorites.includes(item.id) ? " selected" : ""}`} onClick={() => toggleFavorite(item)} aria-label={`${favorites.includes(item.id) ? "Remove" : "Add"} ${item.name} ${favorites.includes(item.id) ? "from" : "to"} favorites`} aria-pressed={favorites.includes(item.id)}>♥</button>
                </div>
                <div className="menu-info">
                  <div className="menu-name-row">
                    <h2>{item.name}</h2>
                    <span className="price">
                      {item.marked_price_minor && item.marked_price_minor > item.price_minor && <del>KSh {formatKes(item.marked_price_minor)}</del>}
                      KSh {formatKes(item.price_minor)}
                    </span>
                  </div>
                  <p>{item.description}</p>
                  {item.points_eligible && <p className="rewards-note">Eligible paid orders earn points you can redeem for available food and drink rewards.</p>}
                  <div className="rating-row">
                    <span className="rating-label">{item.rating_count ? `${item.rating_average.toFixed(1)} · ${item.rating_count}` : "Be first to rate"}</span>
                    <div className="rating-stars" role="group" aria-label={`Rate ${item.name}`}>
                      {[1, 2, 3, 4, 5].map((rating) => (
                        <button key={rating} className={`rating-star${Math.round(item.rating_average) >= rating ? " selected" : ""}`} disabled={ratingPending === item.id} aria-label={`Rate ${item.name} ${rating} star${rating === 1 ? "" : "s"}`} onClick={() => void rateItem(item, rating)}>★</button>
                      ))}
                    </div>
                  </div>
                  <button className="add-button" disabled={busy || menuUnavailable} onClick={() => addToCart(item)}>
                    <span>{menuUnavailable ? "Unavailable" : "Add to order"}</span><span aria-hidden="true">+</span>
                  </button>
                </div>
              </article>
            ))}
            {!displayedMenu.length && <p className="menu-loading">{menuLoading ? "Loading today’s menu…" : menuUnavailable ? "The menu is temporarily unavailable. Please try again later." : showFavorites ? "No favorites yet. Tap a heart to save a dish." : menu.length ? "No dishes match your search." : "No dishes have been posted yet."}</p>}
          </div>
          <p className="rating-disclaimer">Sign in to rate a dish. Ratings reflect customer feedback.</p>
        </section>
        <aside id="order-panel" className="cart">
          <div className="cart-heading"><div><span className="eyebrow">YOUR SELECTION</span><h2>Your order</h2></div><span className="order-counter">{cart.reduce((count, line) => count + line.quantity, 0)}</span></div>
          {cart.length === 0 ? (
            <div className="cart-empty"><span className="empty-bag" aria-hidden="true">▱</span><strong>Your order is empty</strong><span>Add a dish and it will appear here.</span></div>
          ) : cart.map(({ item, quantity }) => (
            <div className="cart-line" key={item.id}>
              <span className="cart-item-name">{item.name}<small>KSh {(item.price_minor / 100).toLocaleString("en-KE")} each</small></span>
              <span className="quantity-controls">
                <button aria-label={`Remove one ${item.name}`} onClick={() => setCart((current) => current.flatMap((line) => line.item.id !== item.id ? [line] : line.quantity > 1 ? [{ ...line, quantity: line.quantity - 1 }] : []))}>−</button>
                <span>{quantity}</span>
                <button aria-label={`Add one ${item.name}`} onClick={() => addToCart(item)}>+</button>
              </span>
            </div>
          ))}
          <div className="order-type-wrap"><label htmlFor="order-type">Order type</label>
            <select id="order-type" className="order-mode" value={orderType} disabled={busy} onChange={(event) => setOrderType(event.target.value as "takeaway" | "dine_in")}>
              <option value="takeaway">Takeaway</option><option value="dine_in">Dine in · Table 1</option>
            </select>
          </div>
          <div className="cart-total"><span>Subtotal</span><strong>KSh {(total / 100).toLocaleString("en-KE")}</strong></div>
          <p className="payment-method"><span className="demo-mark">D</span><span><strong>Demo payment</strong><small>Payment simulation</small></span><span className="payment-arrow">›</span></p>
          <button className="pay-button" disabled={!cart.length || busy || menuUnavailable} onClick={() => void checkout()}>
            {busy ? "Processing…" : `Pay KSh ${(total / 100).toLocaleString("en-KE")}`} <span aria-hidden="true">→</span>
          </button>
          <p className="payment-disclaimer">Local demo payment only. Live M-Pesa is not connected.</p>
          {user && <p className="signed-in-note">Signed in as {user.name}</p>}
        </aside>
      </div>
      <nav className="mobile-nav" aria-label="Main navigation">
        <a className="mobile-nav-link active" href="#menu" aria-label="Home"><span aria-hidden="true">⌂</span><small>Home</small></a>
        <button className="mobile-nav-link" onClick={() => user ? void openRewards() : (setAuthMode("login"), setShowAuth(true))} aria-label="Account and rewards"><span aria-hidden="true">♙</span><small>Account</small></button>
        <button className="mobile-nav-add" onClick={scrollToOrder} aria-label="Go to your order">+</button>
        <button className="mobile-nav-link" onClick={scrollToOrder} aria-label={`Your order, ${cart.reduce((count, line) => count + line.quantity, 0)} items`}><span aria-hidden="true">▤</span><small>Order</small></button>
        <button className={`mobile-nav-link${showFavorites ? " active" : ""}`} onClick={() => { setShowFavorites((current) => !current); document.getElementById("menu")?.scrollIntoView({ behavior: "smooth", block: "start" }); }} aria-label="Favorites" aria-pressed={showFavorites}><span aria-hidden="true">♥</span><small>Saved</small></button>
      </nav>
      {showRewards && user && (
        <div className="loyalty-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowRewards(false); }}>
          <section className="loyalty-modal" role="dialog" aria-modal="true" aria-labelledby="loyalty-title">
            <header className="loyalty-modal-header">
              <div><span className="eyebrow">YOUR MERRYLAND ACCOUNT</span><h2 id="loyalty-title">My account &amp; rewards</h2><p>Welcome, {user.name.split(" ")[0]}.</p></div>
              <button className="modal-close" type="button" aria-label="Close rewards" onClick={() => setShowRewards(false)}>×</button>
            </header>
            {error && <p className="notice error" role="alert">{error}</p>}
            {loyaltyBusy && !loyaltyDashboard ? <p className="loyalty-loading">Loading your rewards…</p> : loyaltyDashboard && (
              <>
                <section className="account-profile" aria-labelledby="account-profile-title">
                  <div className="account-profile-heading">
                    <div className="account-avatar" aria-label={`${user.name} profile photo`}>
                      {user.profile_image_url
                        ? <img src={user.profile_image_url} alt="" />
                        : <span aria-hidden="true">{user.name.trim().charAt(0).toUpperCase()}</span>}
                    </div>
                    <div className="account-profile-title">
                      <span className="eyebrow">MEMBER PROFILE</span>
                      <h3 id="account-profile-title">{user.name}</h3>
                      <p>Your details and delivery information</p>
                    </div>
                    <div className="account-member-since"><span>MEMBER SINCE</span><strong>{new Date(user.created_at).toLocaleDateString("en-KE", { month: "short", year: "numeric" })}</strong></div>
                  </div>
                  <form className="account-profile-form" onSubmit={(event) => void saveProfile(event)}>
                    <div className="account-photo-controls">
                      <label className="account-photo-upload">
                        <input type="file" accept="image/jpeg,image/png,image/webp" disabled={profileBusy} onChange={(event) => { void uploadProfilePhoto(event.target.files?.[0]); event.target.value = ""; }} />
                        {user.profile_image_url ? "Change profile photo" : "Add profile photo"}
                      </label>
                      {user.profile_image_url && <button type="button" className="account-photo-remove" disabled={profileBusy} onClick={() => void removeProfilePhoto()}>Remove</button>}
                      <span>JPG, PNG or WebP · up to 5 MB</span>
                    </div>
                    <div className="account-profile-fields">
                      <label>Full name<input value={profileDraft.name} onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })} minLength={2} maxLength={120} autoComplete="name" required /></label>
                      <label>Phone number<input type="tel" value={profileDraft.phone} onChange={(event) => setProfileDraft({ ...profileDraft, phone: event.target.value })} maxLength={32} autoComplete="tel" placeholder="Add a phone number" /></label>
                      <label className="account-email-field">Email address<input value={user.email} readOnly aria-describedby="account-email-note" /><small id="account-email-note">Email is kept read-only until verification is available.</small></label>
                      <label className="account-address-field">Delivery address<textarea value={profileDraft.delivery_address} onChange={(event) => setProfileDraft({ ...profileDraft, delivery_address: event.target.value })} maxLength={500} rows={2} autoComplete="street-address" placeholder="Add your preferred delivery location" /></label>
                    </div>
                    {profileNotice && <p className="account-profile-notice" role="status">{profileNotice}</p>}
                    <div className="account-profile-actions">
                      <button type="button" className="admin-quiet-button" onClick={signOut}>Sign out</button>
                      <button className="admin-primary-button" disabled={profileBusy}>{profileBusy ? "Saving…" : "Save profile"}</button>
                    </div>
                  </form>
                </section>
                <div className="loyalty-summary-grid">
                  <article className="loyalty-summary-card">
                    <span className="eyebrow">STANDARD REWARDS</span>
                    <strong>{loyaltyDashboard.standard.balance}<small> pts</small></strong>
                    <span>{loyaltyDashboard.standard.lifetime_earned} lifetime points earned</span>
                    <div className="loyalty-progress" role="progressbar" aria-label="Standard rewards progress" aria-valuemin={0} aria-valuemax={loyaltyDashboard.standard.redeem_threshold} aria-valuenow={loyaltyDashboard.standard.progress}>
                      <i style={{ width: `${Math.min(100, loyaltyDashboard.standard.progress / loyaltyDashboard.standard.redeem_threshold * 100)}%` }} />
                    </div>
                    <small>{Math.max(0, loyaltyDashboard.standard.redeem_threshold - loyaltyDashboard.standard.balance)} points to unlock rewards</small>
                  </article>
                  <article className="loyalty-summary-card vip-summary-card">
                    <span className="eyebrow">MERRYLAND VIP</span>
                    <strong>{loyaltyDashboard.vip.lifetime_earned}<small> / {loyaltyDashboard.vip.qualification_threshold} pts</small></strong>
                    <span>{loyaltyDashboard.vip.status} membership</span>
                    <div className="loyalty-progress" role="progressbar" aria-label="VIP membership progress" aria-valuemin={0} aria-valuemax={loyaltyDashboard.vip.qualification_threshold} aria-valuenow={loyaltyDashboard.vip.progress}>
                      <i style={{ width: `${Math.min(100, loyaltyDashboard.vip.progress / loyaltyDashboard.vip.qualification_threshold * 100)}%` }} />
                    </div>
                    <small>VIP points are separate and cannot be redeemed.</small>
                  </article>
                </div>
                {loyaltyDashboard.vip.qualified && loyaltyDashboard.vip.membership_number && (
                  <section className="vip-card">
                    <div><span className="eyebrow">MERRYLAND · VIP MEMBER</span><h3>{user.name}</h3><p>Membership no. {loyaltyDashboard.vip.membership_number}</p><strong>{loyaltyDashboard.vip.status}</strong></div>
                    <QRCodeSVG value={`VIP:${loyaltyDashboard.vip.membership_number}`} size={112} level="M" includeMargin />
                  </section>
                )}
                <section className="loyalty-section">
                  <div className="loyalty-section-heading"><div><span className="eyebrow">EARNED WITH YOUR VISITS</span><h3>Food &amp; drink rewards</h3></div><span>{loyaltyDashboard.standard.balance} pts available</span></div>
                  {loyaltyDashboard.standard.balance < loyaltyDashboard.standard.redeem_threshold && <p className="loyalty-hint">Reach {loyaltyDashboard.standard.redeem_threshold} standard points to unlock the rewards catalogue.</p>}
                  <div className="loyalty-reward-grid">
                    {loyaltyDashboard.standard.rewards.filter((reward) => reward.available).map((reward) => (
                      <article className="loyalty-reward-card" key={reward.id}>
                        {reward.image_url ? <img src={reward.image_url} alt="" /> : <div className="loyalty-reward-placeholder" aria-hidden="true">M</div>}
                        <div><h4>{reward.name}</h4><p>{reward.description || reward.conditions || "A Merryland treat, redeemed with points."}</p><strong>{reward.points_cost} points</strong>
                          <button className="admin-primary-button" disabled={loyaltyBusy || loyaltyDashboard.standard.balance < loyaltyDashboard.standard.redeem_threshold || loyaltyDashboard.standard.balance < reward.points_cost} onClick={() => void redeemLoyaltyReward(reward.id)}>Redeem reward</button>
                        </div>
                      </article>
                    ))}
                    {!loyaltyDashboard.standard.rewards.some((reward) => reward.available) && <p className="loyalty-hint">New food and drink rewards will appear here.</p>}
                  </div>
                </section>
                {loyaltyDashboard.redemptions.some((redemption) => redemption.status === "pending") && (
                  <section className="loyalty-section">
                    <div className="loyalty-section-heading"><div><span className="eyebrow">READY TO SHOW STAFF</span><h3>Your reward codes</h3></div></div>
                    <div className="loyalty-code-list">{loyaltyDashboard.redemptions.filter((redemption) => redemption.status === "pending").map((redemption) => (
                      <article className="loyalty-code-card" key={redemption.id}>
                        <QRCodeSVG value={redemption.code} size={100} level="M" includeMargin />
                        <div><h4>{redemption.reward_name}</h4><p>Code: <strong>{redemption.code}</strong></p><span>{redemption.points_cost} points · pending staff confirmation</span>
                          <button className="admin-quiet-button" disabled={loyaltyBusy} onClick={() => void cancelLoyaltyRedemption(redemption.id)}>Cancel reservation</button>
                        </div>
                      </article>
                    ))}</div>
                  </section>
                )}
                <section className="loyalty-section">
                  <div className="loyalty-section-heading"><div><span className="eyebrow">VIP WEEKEND BENEFIT</span><h3>{loyaltyDashboard.vip.weekend_benefit.name}</h3></div></div>
                  <p className="loyalty-hint">{loyaltyDashboard.vip.weekend_benefit.description} Available {loyaltyDashboard.vip.weekend_benefit.days.join(" & ")} from {loyaltyDashboard.vip.weekend_benefit.start} to {loyaltyDashboard.vip.weekend_benefit.end} ({loyaltyDashboard.vip.weekend_benefit.timezone}). One claim per weekend.</p>
                  {loyaltyDashboard.vip.weekend_benefit.current_claim?.status === "pending" ? (
                    <article className="loyalty-code-card">
                      <QRCodeSVG value={loyaltyDashboard.vip.weekend_benefit.current_claim.code} size={100} level="M" includeMargin />
                      <div><h4>{loyaltyDashboard.vip.weekend_benefit.current_claim.reward_name}</h4><p>Code: <strong>{loyaltyDashboard.vip.weekend_benefit.current_claim.code}</strong></p><span>Show staff to confirm collection.</span></div>
                    </article>
                  ) : (
                    <button className="admin-primary-button" disabled={loyaltyBusy || !loyaltyDashboard.vip.weekend_benefit.claim_available} onClick={() => void claimWeekendBenefit()}>
                      {loyaltyDashboard.vip.status !== "Active" ? "Qualify for VIP to unlock" : loyaltyDashboard.vip.weekend_benefit.claim_available ? "Claim weekend nyama choma" : "Available during configured weekend hours"}
                    </button>
                  )}
                </section>
                <section className="loyalty-section">
                  <div className="loyalty-section-heading"><div><span className="eyebrow">YOUR ACTIVITY</span><h3>Points earned per purchase</h3></div><button className="admin-quiet-button" onClick={() => { setShowRewards(false); document.getElementById("order-panel")?.scrollIntoView({ behavior: "smooth" }); }}>Earn more points</button></div>
                  {loyaltyDashboard.orders.length ? <div className="loyalty-history-list">{loyaltyDashboard.orders.map((order) => (
                    <article key={order.id}><div><strong>{order.order_number}</strong><span>{new Date(order.created_at).toLocaleDateString("en-KE")} · {order.status}</span></div><div><strong>KSh {formatKes(order.total_minor)}</strong><span>+{order.standard_points} standard · +{order.vip_points} VIP pts</span></div></article>
                  ))}</div> : <p className="loyalty-hint">Completed paid orders will appear here with the points they earned.</p>}
                </section>
                <section className="loyalty-section">
                  <div className="loyalty-section-heading"><div><span className="eyebrow">POINTS LEDGER</span><h3>Recent activity</h3></div></div>
                  {loyaltyDashboard.transactions.length ? <div className="loyalty-history-list">{loyaltyDashboard.transactions.slice(0, 15).map((entry) => (
                    <article key={entry.id}><div><strong>{entry.description}</strong><span>{entry.track === "vip" ? "VIP" : "Standard"} · {entry.type} · {new Date(entry.created_at).toLocaleDateString("en-KE")}</span></div><strong className={entry.points < 0 ? "loyalty-negative" : ""}>{entry.points > 0 ? "+" : ""}{entry.points} pts</strong></article>
                  ))}</div> : <p className="loyalty-hint">Your earned points and redemptions will appear here.</p>}
                </section>
              </>
            )}
          </section>
        </div>
      )}
      {showAuth && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowAuth(false); }}>
          <form id="account" className="auth-modal" onSubmit={(event) => void submitAuth(event)}>
            <button className="modal-close" type="button" aria-label="Close sign in" onClick={() => setShowAuth(false)}>×</button>
            <span className="eyebrow">{authMode === "register" ? "JOIN MERRYLAND" : "WELCOME BACK"}</span>
            <h2>{authMode === "register" ? "Create your account" : "Sign in to Merryland"}</h2>
            <p>{authMode === "register" ? "Create an account to continue with your order." : "Sign in to continue with your order."}</p>
            {!busy && <GoogleSignInButton onIdToken={(idToken) => void submitGoogleAuth(idToken)} onError={setError} />}
            <div className="auth-divider"><span />OR CONTINUE WITH EMAIL<span /></div>
            {authMode === "register" && <input className="field" name="name" placeholder="Your name" autoComplete="name" required minLength={2} />}
            {authMode === "register" && <input className="field" name="phone" placeholder="Phone number" type="tel" autoComplete="tel" required minLength={7} />}
            <input className="field" name="email" placeholder="Email address" type="email" autoComplete="email" required />
            <input className="field" name="password" placeholder={authMode === "register" ? "Password (10+ characters)" : "Password"} type="password" autoComplete={authMode === "register" ? "new-password" : "current-password"} required minLength={authMode === "register" ? 10 : 1} />
            <button className="pay-button" disabled={busy}>{busy ? "Please wait…" : authMode === "register" ? "Create account" : "Sign in"}</button>
            <button className="quiet" type="button" onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}>
              {authMode === "register" ? "Already a member? Sign in" : "New here? Create an account"}
            </button>
          </form>
        </div>
      )}
    </main>
  );
}
