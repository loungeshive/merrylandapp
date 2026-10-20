"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";
const CATEGORIES = ["Food", "Drinks", "Bites"] as const;
type Category = (typeof CATEGORIES)[number];
type CategoryFilter = "All" | Category | "Under KSh 500";
type MenuItem = {
  id: string;
  category_name: Category;
  name: string;
  description: string;
  price_minor: number;
  marked_price_minor: number | null;
  image_url: string;
  prep_minutes: number;
  available: boolean;
  rating_average: number;
  rating_count: number;
  points_eligible: boolean;
};
type Draft = {
  category_name: Category;
  name: string;
  description: string;
  price_kes: string;
  marked_price_kes: string;
  prep_minutes: string;
  image_url: string;
  available: boolean;
  points_eligible: boolean;
};
type LoyaltySettings = {
  standard_min_spend_kes: number;
  standard_award_points: number;
  standard_redeem_threshold: number;
  vip_min_spend_kes: number;
  vip_award_points: number;
  vip_qualification_points: number;
  weekend_days: string[];
  weekend_start: string;
  weekend_end: string;
  weekend_reward_name: string;
  weekend_reward_description: string;
  timezone_name: string;
};
type AdminReward = { id: string; menu_item_id: string | null; name: string; description: string; points_cost: number; conditions: string; available: boolean };
type LoyaltyMember = { customer_id: string; name: string; email: string; phone: string | null; delivery_address: string | null; created_at: string; standard_balance: number; standard_earned: number; vip_balance: number; vip_earned: number; vip_membership_number: string | null; vip_status: string };
type LoyaltyAnalytics = { members: number; active_vip_members: number; standard_points_outstanding: number; vip_points_issued: number; pending_reward_redemptions: number; pending_vip_claims: number };
type AdminRedemptions = { rewards: { id: string; code: string; reward_name: string; points_cost: number; status: string; customer_id: string }[]; vip_weekends: { id: string; code: string; reward_name: string; status: string; customer_id: string }[] };
type AdminAuditLog = { id: string; admin_actor: string; action: string; entity_type: string; entity_id: string; reason: string; details: Record<string, unknown>; created_at: string };
type MemberActivity = { transactions: { track: string; type: string; points: number; description: string; reason: string | null; admin_actor: string | null; created_at: string }[]; orders: { order_number: string; total_minor: number; status: string; created_at: string; items: { name: string; quantity: number; eligible: boolean }[]; awards: { track: string; points: number }[] }[] };
const DEFAULT_LOYALTY_SETTINGS: LoyaltySettings = {
  standard_min_spend_kes: 200,
  standard_award_points: 5,
  standard_redeem_threshold: 200,
  vip_min_spend_kes: 1000,
  vip_award_points: 10,
  vip_qualification_points: 100,
  weekend_days: ["Saturday", "Sunday"],
  weekend_start: "12:00",
  weekend_end: "22:00",
  weekend_reward_name: "Complimentary nyama choma",
  weekend_reward_description: "One complimentary portion per eligible VIP per weekend.",
  timezone_name: "Africa/Nairobi",
};

const emptyDraft = (): Draft => ({
  category_name: "Food",
  name: "",
  description: "",
  price_kes: "",
  marked_price_kes: "",
  prep_minutes: "15",
  image_url: "",
  available: true,
  points_eligible: true,
});
const formatKes = (minor: number) => (minor / 100).toLocaleString("en-KE");

export default function AdminPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [products, setProducts] = useState<MenuItem[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("All");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [section, setSection] = useState<"menu" | "loyalty">("menu");
  const [loyaltySettings, setLoyaltySettings] = useState<LoyaltySettings>(DEFAULT_LOYALTY_SETTINGS);
  const [loyaltyRewards, setLoyaltyRewards] = useState<AdminReward[]>([]);
  const [loyaltyMembers, setLoyaltyMembers] = useState<LoyaltyMember[]>([]);
  const [loyaltyAnalytics, setLoyaltyAnalytics] = useState<LoyaltyAnalytics | null>(null);
  const [loyaltyRedemptions, setLoyaltyRedemptions] = useState<AdminRedemptions>({ rewards: [], vip_weekends: [] });
  const [loyaltyAuditLogs, setLoyaltyAuditLogs] = useState<AdminAuditLog[]>([]);
  const [memberActivity, setMemberActivity] = useState<MemberActivity | null>(null);
  const [activityMemberId, setActivityMemberId] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [verifyCode, setVerifyCode] = useState("");
  const [verifiedCode, setVerifiedCode] = useState("");
  const [rewardDraft, setRewardDraft] = useState({ name: "", description: "", menu_item_id: "", points_cost: "", conditions: "", available: true });
  const [rewardEditingId, setRewardEditingId] = useState<string | null>(null);
  const [adjustment, setAdjustment] = useState({ customer_id: "", track: "standard", points: "", reason: "" });

  useEffect(() => {
    if (!imageFile) {
      setImagePreview(draft.image_url);
      return;
    }
    const objectUrl = URL.createObjectURL(imageFile);
    setImagePreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [draft.image_url, imageFile]);

  const visibleProducts = useMemo(() => products.filter((product) => {
    if (categoryFilter === "Under KSh 500") return product.price_minor < 50_000;
    return categoryFilter === "All" || product.category_name === categoryFilter;
  }), [categoryFilter, products]);

  async function loadProducts(accessToken: string) {
    const response = await fetch(`${API}/admin/menu`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail ?? "Could not load menu products.");
    setProducts(result);
  }

  async function adminRequest<T>(path: string, accessToken: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        Authorization: "Bearer " + accessToken,
        ...options.headers,
      },
    });
    const result = response.status === 204 ? null : await response.json();
    if (!response.ok) throw new Error(result?.detail ?? "Administrator request failed.");
    return result as T;
  }

  async function loadLoyalty(accessToken: string, searchTerm = memberSearch) {
    const membersPath = "/admin/loyalty/members" + (searchTerm ? "?search=" + encodeURIComponent(searchTerm) : "");
    const [configuration, rewards, members, analytics, redemptions, auditLogs] = await Promise.all([
      adminRequest<LoyaltySettings>("/admin/loyalty/settings", accessToken),
      adminRequest<AdminReward[]>("/admin/loyalty/rewards", accessToken),
      adminRequest<LoyaltyMember[]>(membersPath, accessToken),
      adminRequest<LoyaltyAnalytics>("/admin/loyalty/analytics", accessToken),
      adminRequest<AdminRedemptions>("/admin/loyalty/redemptions", accessToken),
      adminRequest<AdminAuditLog[]>("/admin/loyalty/audit-logs", accessToken),
    ]);
    setLoyaltySettings(configuration);
    setLoyaltyRewards(rewards);
    setLoyaltyMembers(members);
    setLoyaltyAnalytics(analytics);
    setLoyaltyRedemptions(redemptions);
    setLoyaltyAuditLogs(auditLogs);
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API}/admin/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Admin sign-in failed.");
      setToken(result.access_token);
      await loadProducts(result.access_token);
      await loadLoyalty(result.access_token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Admin sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  function startEditing(product: MenuItem) {
    setEditingId(product.id);
    setDraft({
      category_name: product.category_name,
      name: product.name,
      description: product.description,
      price_kes: (product.price_minor / 100).toFixed(2),
      marked_price_kes: product.marked_price_minor ? (product.marked_price_minor / 100).toFixed(2) : "",
      prep_minutes: String(product.prep_minutes),
      image_url: product.image_url,
      available: product.available,
      points_eligible: product.points_eligible,
    });
    setImageFile(null);
    setError("");
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearDraft() {
    setEditingId(null);
    setDraft(emptyDraft());
    setImageFile(null);
  }

  async function saveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      let imageUrl = draft.image_url;
      if (imageFile) {
        const imageData = new FormData();
        imageData.append("image", imageFile);
        const upload = await fetch(`${API}/admin/menu/images`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: imageData,
        });
        const uploaded = await upload.json();
        if (!upload.ok) throw new Error(uploaded.detail ?? "Image upload failed.");
        imageUrl = uploaded.image_url;
      }
      if (!imageUrl) throw new Error("Choose a product image before posting.");
      const sellingPrice = Math.round(Number(draft.price_kes) * 100);
      const markedPrice = draft.marked_price_kes ? Math.round(Number(draft.marked_price_kes) * 100) : null;
      if (!Number.isSafeInteger(sellingPrice) || sellingPrice <= 0) throw new Error("Enter a valid selling price.");
      if (markedPrice !== null && (!Number.isSafeInteger(markedPrice) || markedPrice < sellingPrice)) {
        throw new Error("Marked price must be at least the selling price.");
      }
      const payload = {
        category_name: draft.category_name,
        name: draft.name.trim(),
        description: draft.description.trim(),
        price_minor: sellingPrice,
        marked_price_minor: markedPrice,
        image_url: imageUrl,
        prep_minutes: Number(draft.prep_minutes),
        available: draft.available,
        points_eligible: draft.points_eligible,
      };
      const response = await fetch(`${API}/admin/menu${editingId ? `/${editingId}` : ""}`, {
        method: editingId ? "PUT" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "The menu product could not be saved.");
      await loadProducts(token);
      await loadLoyalty(token);
      setNotice(editingId ? "Menu product updated." : "Menu product posted.");
      clearDraft();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The menu product could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function hideProduct(product: MenuItem) {
    if (!window.confirm(`Remove ${product.name} from the customer menu?`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${API}/admin/menu/${product.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail ?? "The menu product could not be removed.");
      }
      await loadProducts(token);
      setNotice("Product removed from the customer menu. Its order history has been preserved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The menu product could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  async function restoreProduct(product: MenuItem) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${API}/admin/menu/${product.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          category_name: product.category_name,
          name: product.name,
          description: product.description,
          price_minor: product.price_minor,
          marked_price_minor: product.marked_price_minor,
          image_url: product.image_url,
          prep_minutes: product.prep_minutes,
          available: true,
          points_eligible: product.points_eligible,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "The product could not be restored.");
      await loadProducts(token);
      setNotice(`${product.name} is back on the customer menu.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The product could not be restored.");
    } finally {
      setBusy(false);
    }
  }

  async function saveLoyaltyConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await adminRequest<LoyaltySettings>("/admin/loyalty/settings", token, {
        method: "PUT",
        body: JSON.stringify(loyaltySettings),
      });
      setLoyaltySettings(updated);
      setNotice("Loyalty rules and VIP serving schedule saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Loyalty settings could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveReward(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        ...rewardDraft,
        menu_item_id: rewardDraft.menu_item_id || null,
        points_cost: Number(rewardDraft.points_cost),
        name: rewardDraft.name.trim(),
        description: rewardDraft.description.trim(),
        conditions: rewardDraft.conditions.trim(),
      };
      const saved = await adminRequest<AdminReward>(
        `/admin/loyalty/rewards${rewardEditingId ? `/${rewardEditingId}` : ""}`,
        token,
        { method: rewardEditingId ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      await loadLoyalty(token);
      setRewardDraft({ name: "", description: "", menu_item_id: "", points_cost: "", conditions: "", available: true });
      setRewardEditingId(null);
      setNotice(`${saved.name} reward ${rewardEditingId ? "updated" : "added"}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The reward could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function hideReward(reward: AdminReward) {
    if (!window.confirm(`Hide the ${reward.name} reward from customers?`)) return;
    setBusy(true);
    setError("");
    try {
      await adminRequest<null>(`/admin/loyalty/rewards/${reward.id}`, token, { method: "DELETE" });
      await loadLoyalty(token);
      setNotice("Reward hidden from the customer catalogue.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The reward could not be hidden.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyLoyaltyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setVerifiedCode("");
    try {
      const result = await adminRequest<{ type: string; customer_name?: string; reward_name?: string; membership_number?: string; status: string }>(
        "/admin/loyalty/verify",
        token,
        { method: "POST", body: JSON.stringify({ code: verifyCode.trim() }) },
      );
      setVerifiedCode(
        result.type === "vip_card"
          ? `Valid VIP membership: ${result.customer_name} Â· ${result.membership_number} Â· ${result.status}`
          : `${result.reward_name} confirmed and marked as redeemed.`,
      );
      setVerifyCode("");
      await loadLoyalty(token);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The code could not be verified.");
    } finally {
      setBusy(false);
    }
  }

  async function searchLoyaltyMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await loadLoyalty(token, memberSearch);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Customer search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function viewMemberActivity(member: LoyaltyMember) {
    setBusy(true);
    setError("");
    try {
      const activity = await adminRequest<MemberActivity>(`/admin/loyalty/members/${member.customer_id}/activity`, token);
      setMemberActivity(activity);
      setActivityMemberId(member.customer_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Customer activity could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  async function exportLoyaltyReport() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API}/admin/loyalty/export`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail ?? "Loyalty report export failed.");
      }
      const downloadUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = "merryland-loyalty-members.csv";
      link.click();
      URL.revokeObjectURL(downloadUrl);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Loyalty report export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function savePointAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await adminRequest(`/admin/loyalty/members/${adjustment.customer_id}/adjustments`, token, {
        method: "POST",
        body: JSON.stringify({ track: adjustment.track, points: Number(adjustment.points), reason: adjustment.reason.trim() }),
      });
      await loadLoyalty(token);
      setAdjustment({ customer_id: "", track: "standard", points: "", reason: "" });
      setNotice("Audited points adjustment recorded.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Points adjustment failed.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleLoyaltySuspension(member: LoyaltyMember) {
    const suspended = member.vip_status !== "Suspended";
    const reason = suspended ? window.prompt(`Reason for suspending ${member.name}'s loyalty account:`) : "";
    if (suspended && reason === null) return;
    setBusy(true);
    setError("");
    try {
      await adminRequest(`/admin/loyalty/members/${member.customer_id}/suspension`, token, {
        method: "PATCH",
        body: JSON.stringify({ suspended, reason: reason ?? "" }),
      });
      await loadLoyalty(token);
      setNotice(suspended ? "Loyalty account suspended." : "Loyalty account reinstated.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The loyalty account status could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    setToken("");
    setProducts([]);
    setLoyaltyRewards([]);
    setLoyaltyMembers([]);
    setLoyaltyAnalytics(null);
    setLoyaltyAuditLogs([]);
    setMemberActivity(null);
    setActivityMemberId("");
    clearDraft();
  }

  if (!token) {
    return (
      <main className="admin-page admin-login-page">
        <a className="admin-brand" href="/">Merryland <span>Rewards</span></a>
        <form className="admin-login-card" onSubmit={(event) => void signIn(event)}>
          <span className="admin-eyebrow">RESTAURANT MANAGEMENT</span>
          <h1>Admin sign in</h1>
          <p>Sign in with the separate administrator account to manage the customer menu.</p>
          {error && <p className="admin-alert error" role="alert">{error}</p>}
          <label>Username<input type="text" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
          <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
          <button className="admin-primary-button" disabled={busy}>{busy ? "Signing inâ€¦" : "Sign in to dashboard"}</button>
          <a className="admin-back-link" href="/">Back to customer menu</a>
        </form>
      </main>
    );
  }

  return (
    <main className="admin-page">
      <header className="admin-header">
        <a className="admin-brand" href="/">Merryland <span>Rewards</span></a>
        <div className="admin-header-actions">
          <div className="admin-section-tabs" role="tablist" aria-label="Admin sections">
            <button className={section === "menu" ? "active" : ""} role="tab" aria-selected={section === "menu"} onClick={() => setSection("menu")}>Menu</button>
            <button className={section === "loyalty" ? "active" : ""} role="tab" aria-selected={section === "loyalty"} onClick={() => setSection("loyalty")}>Loyalty &amp; VIP</button>
          </div>
          <button className="admin-quiet-button" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <div className="admin-content">
        {(error || notice) && <p className={`admin-alert${error ? " error" : ""}`} role="status">{error || notice}</p>}
        {section === "menu" ? <>
        <div className="admin-page-heading">
          <div>
            <span className="admin-eyebrow">MERRYLAND RESTAURANT</span>
            <h1>Menu management</h1>
            <p>Publish dishes, drinks and bites to the customer homepage.</p>
          </div>
          <a className="admin-preview-link" href="/">View customer menu</a>
        </div>
        <div className="admin-columns">
          <section className="admin-panel">
            <div className="admin-panel-heading">
              <div>
                <span className="admin-eyebrow">{editingId ? "EDIT MENU ITEM" : "NEW MENU ITEM"}</span>
                <h2>{editingId ? "Update product" : "Add a product"}</h2>
              </div>
            </div>
            <form className="product-form" onSubmit={(event) => void saveProduct(event)}>
              <label>Product name<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} maxLength={120} required /></label>
              <label>Category
                <select value={draft.category_name} onChange={(event) => setDraft({ ...draft, category_name: event.target.value as Category })}>
                  {CATEGORIES.map((category) => <option key={category}>{category}</option>)}
                </select>
              </label>
              <div className="admin-price-fields">
                <label>Selling price (KSh)<input type="number" min="0.01" step="0.01" value={draft.price_kes} onChange={(event) => setDraft({ ...draft, price_kes: event.target.value })} required /></label>
                <label>Marked price (KSh)<input type="number" min="0.01" step="0.01" value={draft.marked_price_kes} onChange={(event) => setDraft({ ...draft, marked_price_kes: event.target.value })} placeholder="Optional" /></label>
              </div>
              <p className="admin-hint">Set a marked price above the selling price to display a special offer.</p>
              <label>Description<textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} rows={4} maxLength={500} /></label>
              <label>Preparation time (minutes)<input type="number" min="1" max="600" value={draft.prep_minutes} onChange={(event) => setDraft({ ...draft, prep_minutes: event.target.value })} required /></label>
              <label className="admin-upload-label">
                Product image
                <span className="admin-upload-box">
                  {imagePreview ? <img src={imagePreview} alt="Product preview" /> : <span className="admin-upload-placeholder">Choose a JPG, PNG, or WebP image (max 5 MB)</span>}
                  <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setImageFile(event.target.files?.[0] ?? null)} />
                </span>
              </label>
              <label className="admin-checkbox"><input type="checkbox" checked={draft.available} onChange={(event) => setDraft({ ...draft, available: event.target.checked })} />Show this product on the customer menu</label>
              <label className="admin-checkbox"><input type="checkbox" checked={draft.points_eligible} onChange={(event) => setDraft({ ...draft, points_eligible: event.target.checked })} />Include this product in qualifying loyalty spend</label>
              <div className="admin-form-actions">
                <button className="admin-primary-button" disabled={busy}>{busy ? "Savingâ€¦" : editingId ? "Update product" : "Post product"}</button>
                {editingId && <button className="admin-quiet-button" type="button" onClick={clearDraft}>Cancel</button>}
              </div>
            </form>
          </section>

          <section className="admin-panel admin-products-panel">
            <div className="admin-panel-heading">
              <div>
                <span className="admin-eyebrow">LIVE CATALOG</span>
                <h2>Products <span className="admin-product-count">{visibleProducts.length}</span></h2>
              </div>
            </div>
            <div className="admin-product-filters" role="group" aria-label="Filter products">
              {(["All", ...CATEGORIES, "Under KSh 500"] as CategoryFilter[]).map((category) => (
                <button key={category} className={categoryFilter === category ? "active" : ""} onClick={() => setCategoryFilter(category)} aria-pressed={categoryFilter === category}>{category}</button>
              ))}
            </div>
            <div className="admin-product-list">
              {visibleProducts.length ? visibleProducts.map((product) => (
                <article className={`admin-product${product.available ? "" : " inactive"}`} key={product.id}>
                  <img src={product.image_url} alt="" />
                  <div className="admin-product-info">
                    <div className="admin-product-title-row">
                      <h3>{product.name}</h3>
                      <span className={`admin-product-status${product.available ? "" : " hidden"}`}>{product.available ? "Live" : "Hidden"}</span>
                    </div>
                    <span className="admin-product-category">{product.category_name}</span>
                    <div className="admin-product-price">
                      {product.marked_price_minor && product.marked_price_minor > product.price_minor && <del>KSh {formatKes(product.marked_price_minor)}</del>}
                      <strong>KSh {formatKes(product.price_minor)}</strong>
                    </div>
                    <p className="admin-rating-summary">{product.rating_count ? `${product.rating_average.toFixed(1)} â˜… Â· ${product.rating_count} customer ratings` : "No customer ratings yet"}</p>
                    <div className="admin-product-actions">
                      <button onClick={() => startEditing(product)}>Edit</button>
                      {product.available
                        ? <button className="danger" disabled={busy} onClick={() => void hideProduct(product)}>Delete</button>
                        : <button className="restore" disabled={busy} onClick={() => void restoreProduct(product)}>Restore</button>}
                    </div>
                  </div>
                </article>
              )) : <p className="admin-empty-state">No products in this view yet. Post a product to get started.</p>}
            </div>
          </section>
        </div>
        </> : (
          <div className="admin-loyalty">
            <div className="admin-page-heading">
              <div>
                <span className="admin-eyebrow">CUSTOMER RETENTION</span>
                <h1>Loyalty &amp; VIP management</h1>
                <p>Configure earning rules, manage rewards, verify claims, and review member activity.</p>
              </div>
              <div className="admin-loyalty-heading-actions"><button className="admin-quiet-button" disabled={busy} onClick={() => void exportLoyaltyReport()}>Export member report</button><a className="admin-preview-link" href="/">View customer menu</a></div>
            </div>
            {loyaltyAnalytics && <div className="admin-loyalty-metrics">
              <article><span>Registered members</span><strong>{loyaltyAnalytics.members}</strong></article>
              <article><span>Active VIP members</span><strong>{loyaltyAnalytics.active_vip_members}</strong></article>
              <article><span>Standard points outstanding</span><strong>{loyaltyAnalytics.standard_points_outstanding}</strong></article>
              <article><span>VIP points earned</span><strong>{loyaltyAnalytics.vip_points_issued}</strong></article>
              <article><span>Pending reward codes</span><strong>{loyaltyAnalytics.pending_reward_redemptions}</strong></article>
              <article><span>Pending VIP claims</span><strong>{loyaltyAnalytics.pending_vip_claims}</strong></article>
            </div>}
            <div className="admin-loyalty-columns">
              <section className="admin-panel">
                <div className="admin-panel-heading"><div><span className="admin-eyebrow">EARNING &amp; REDEMPTION</span><h2>Loyalty rules</h2></div></div>
                <form className="product-form" onSubmit={(event) => void saveLoyaltyConfiguration(event)}>
                  <div className="admin-loyalty-rule-grid">
                    <label>Standard minimum spend (KSh)<input type="number" min="0" value={loyaltySettings.standard_min_spend_kes} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, standard_min_spend_kes: Number(event.target.value) })} required /></label>
                    <label>Standard award (points/order)<input type="number" min="1" value={loyaltySettings.standard_award_points} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, standard_award_points: Number(event.target.value) })} required /></label>
                    <label>Reward unlock threshold<input type="number" min="1" value={loyaltySettings.standard_redeem_threshold} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, standard_redeem_threshold: Number(event.target.value) })} required /></label>
                    <label>VIP minimum spend (KSh)<input type="number" min="0" value={loyaltySettings.vip_min_spend_kes} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, vip_min_spend_kes: Number(event.target.value) })} required /></label>
                    <label>VIP award (points/order)<input type="number" min="1" value={loyaltySettings.vip_award_points} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, vip_award_points: Number(event.target.value) })} required /></label>
                    <label>Lifetime VIP qualification points<input type="number" min="1" value={loyaltySettings.vip_qualification_points} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, vip_qualification_points: Number(event.target.value) })} required /></label>
                  </div>
                  <p className="admin-hint">Spend thresholds are strict: an order must exceed the amount. Point awards apply once per verified paid order. Production awards stay disabled until real M-Pesa verification is integrated.</p>
                  <label>VIP weekend benefit name<input value={loyaltySettings.weekend_reward_name} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, weekend_reward_name: event.target.value })} maxLength={120} required /></label>
                  <label>Benefit description<textarea rows={3} value={loyaltySettings.weekend_reward_description} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, weekend_reward_description: event.target.value })} maxLength={500} /></label>
                  <fieldset className="admin-weekend-days"><legend>Eligible days (one claim per calendar week)</legend>
                    {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day) => <label key={day}><input type="checkbox" checked={loyaltySettings.weekend_days.includes(day)} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, weekend_days: event.target.checked ? [...loyaltySettings.weekend_days, day] : loyaltySettings.weekend_days.filter((entry) => entry !== day) })} />{day}</label>)}
                  </fieldset>
                  <div className="admin-loyalty-rule-grid">
                    <label>Serving starts<input type="time" value={loyaltySettings.weekend_start} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, weekend_start: event.target.value })} required /></label>
                    <label>Serving ends<input type="time" value={loyaltySettings.weekend_end} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, weekend_end: event.target.value })} required /></label>
                  </div>
                  <label>Time zone<input value={loyaltySettings.timezone_name} onChange={(event) => setLoyaltySettings({ ...loyaltySettings, timezone_name: event.target.value })} required /></label>
                  <button className="admin-primary-button" disabled={busy}>Save loyalty settings</button>
                </form>
              </section>

              <section className="admin-panel">
                <div className="admin-panel-heading"><div><span className="admin-eyebrow">{rewardEditingId ? "EDIT REWARD" : "STANDARD POINTS CATALOGUE"}</span><h2>{rewardEditingId ? "Update reward" : "Add a reward"}</h2></div></div>
                <form className="product-form" onSubmit={(event) => void saveReward(event)}>
                  <label>Reward name<input value={rewardDraft.name} onChange={(event) => setRewardDraft({ ...rewardDraft, name: event.target.value })} minLength={2} maxLength={120} required /></label>
                  <label>Linked menu item (optional)<select value={rewardDraft.menu_item_id} onChange={(event) => setRewardDraft({ ...rewardDraft, menu_item_id: event.target.value })}><option value="">No linked item</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
                  <label>Points cost<input type="number" min="1" value={rewardDraft.points_cost} onChange={(event) => setRewardDraft({ ...rewardDraft, points_cost: event.target.value })} required /></label>
                  <label>Description<textarea rows={2} value={rewardDraft.description} onChange={(event) => setRewardDraft({ ...rewardDraft, description: event.target.value })} maxLength={500} /></label>
                  <label>Redemption conditions<input value={rewardDraft.conditions} onChange={(event) => setRewardDraft({ ...rewardDraft, conditions: event.target.value })} maxLength={500} /></label>
                  <label className="admin-checkbox"><input type="checkbox" checked={rewardDraft.available} onChange={(event) => setRewardDraft({ ...rewardDraft, available: event.target.checked })} />Available to customers</label>
                  <div className="admin-form-actions"><button className="admin-primary-button" disabled={busy}>{rewardEditingId ? "Update reward" : "Add reward"}</button>{rewardEditingId && <button type="button" className="admin-quiet-button" onClick={() => { setRewardEditingId(null); setRewardDraft({ name: "", description: "", menu_item_id: "", points_cost: "", conditions: "", available: true }); }}>Cancel</button>}</div>
                </form>
                <div className="admin-loyalty-list">{loyaltyRewards.map((reward) => <article key={reward.id}><div><strong>{reward.name}</strong><span>{reward.points_cost} pts Â· {reward.available ? "Available" : "Hidden"}{reward.conditions ? ` Â· ${reward.conditions}` : ""}</span></div><div className="admin-product-actions"><button onClick={() => { setRewardEditingId(reward.id); setRewardDraft({ name: reward.name, description: reward.description, menu_item_id: reward.menu_item_id ?? "", points_cost: String(reward.points_cost), conditions: reward.conditions, available: reward.available }); }}>Edit</button>{reward.available && <button className="danger" disabled={busy} onClick={() => void hideReward(reward)}>Hide</button>}</div></article>)}</div>
              </section>
            </div>

            <section className="admin-panel admin-verification-panel">
              <div className="admin-panel-heading"><div><span className="admin-eyebrow">STAFF REDEMPTION DESK</span><h2>Verify a reward code or VIP card</h2></div></div>
              <form className="admin-verify-form" onSubmit={(event) => void verifyLoyaltyCode(event)}>
                <label>Enter code from customer QR<input value={verifyCode} onChange={(event) => setVerifyCode(event.target.value.toUpperCase())} maxLength={32} placeholder="MR-VIP-…" required /></label>
                <button className="admin-primary-button" disabled={busy}>{busy ? "Verifyingâ€¦" : "Verify code"}</button>
              </form>
              {verifiedCode && <p className="admin-alert" role="status">{verifiedCode}</p>}
            </section>

            <section className="admin-panel">
              <div className="admin-panel-heading"><div><span className="admin-eyebrow">MEMBER ACCOUNTS</span><h2>Search &amp; manage customers</h2></div></div>
              <form className="admin-member-search" onSubmit={(event) => void searchLoyaltyMembers(event)}><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder="Name, email, phone, or VIP membership number" /><button className="admin-primary-button" disabled={busy}>Search</button></form>
              <div className="admin-member-list">{loyaltyMembers.map((member) => <article key={member.customer_id}>
                <div className="admin-member-identity">
                  <strong>{member.name}</strong>
                  <span>Email: {member.email}</span>
                  <span>Mobile: {member.phone || "Not provided"}</span>
                  {member.delivery_address && <span>Delivery address: {member.delivery_address}</span>}
                  <small>Registered {new Date(member.created_at).toLocaleDateString("en-KE", { day: "numeric", month: "short", year: "numeric" })}</small>
                  <small>Standard: {member.standard_balance} available / {member.standard_earned} earned Â· VIP: {member.vip_balance} available / {member.vip_earned} earned</small>
                  {member.vip_membership_number && <small>{member.vip_membership_number} Â· {member.vip_status}</small>}
                </div>
                <div className="admin-product-actions"><button disabled={busy} onClick={() => void viewMemberActivity(member)}>View ledger</button><button disabled={busy} onClick={() => void toggleLoyaltySuspension(member)}>{member.vip_status === "Suspended" ? "Reinstate" : "Suspend"}</button><button onClick={() => setAdjustment({ ...adjustment, customer_id: member.customer_id })}>Adjust points</button></div>
              </article>)}
                {!loyaltyMembers.length && <p className="admin-empty-state">No registered customers match this search.</p>}
              </div>
              {activityMemberId && memberActivity && <section className="admin-member-activity">
                <div className="admin-panel-heading"><h3>Purchase &amp; points activity · {loyaltyMembers.find((member) => member.customer_id === activityMemberId)?.name}</h3><button className="admin-quiet-button" onClick={() => { setActivityMemberId(""); setMemberActivity(null); }}>Close</button></div>
                <h4>Verified paid orders</h4>{memberActivity.orders.map((order) => <article key={order.order_number}><strong>{order.order_number} · KSh {formatKes(order.total_minor)} · {order.status}</strong><span>{order.items.map((item) => `${item.name} ×${item.quantity}${item.eligible ? " (eligible)" : " (excluded)"}`).join(", ")}</span><span>{order.awards.length ? order.awards.map((award) => `${award.track}: +${award.points}`).join(" · ") : "No points awarded"}</span></article>)}
                <h4>Points ledger</h4>{memberActivity.transactions.map((entry, index) => <article key={`${entry.created_at}-${index}`}><strong>{entry.track} · {entry.type} · {entry.points > 0 ? "+" : ""}{entry.points}</strong><span>{entry.description}{entry.reason ? ` · ${entry.reason}` : ""}{entry.admin_actor ? ` · by ${entry.admin_actor}` : ""}</span></article>)}
              </section>}
              {adjustment.customer_id && <form className="admin-adjustment-form" onSubmit={(event) => void savePointAdjustment(event)}>
                <strong>Audited points adjustment for {loyaltyMembers.find((member) => member.customer_id === adjustment.customer_id)?.name}</strong>
                <select value={adjustment.track} onChange={(event) => setAdjustment({ ...adjustment, track: event.target.value })}><option value="standard">Standard points</option><option value="vip">VIP points</option></select>
                <input type="number" value={adjustment.points} onChange={(event) => setAdjustment({ ...adjustment, points: event.target.value })} placeholder="Positive or negative points" required />
                <input value={adjustment.reason} onChange={(event) => setAdjustment({ ...adjustment, reason: event.target.value })} minLength={5} maxLength={500} placeholder="Reason for adjustment" required />
                <button className="admin-primary-button" disabled={busy}>Record audited adjustment</button>
              </form>}
            </section>

            <section className="admin-panel">
              <div className="admin-panel-heading"><div><span className="admin-eyebrow">REDEMPTION HISTORY</span><h2>Pending &amp; completed claims</h2></div></div>
              <div className="admin-loyalty-columns">
                <div className="admin-loyalty-list"><h3>Food and drink rewards</h3>{loyaltyRedemptions.rewards.map((entry) => <article key={entry.id}><div><strong>{entry.reward_name}</strong><span>{entry.customer_id} Â· {entry.points_cost} pts Â· {entry.status}</span></div><code>{entry.code}</code></article>)}</div>
                <div className="admin-loyalty-list"><h3>VIP weekend benefits</h3>{loyaltyRedemptions.vip_weekends.map((entry) => <article key={entry.id}><div><strong>{entry.reward_name}</strong><span>{entry.customer_id} Â· {entry.status}</span></div><code>{entry.code}</code></article>)}</div>
              </div>
            </section>
            <section className="admin-panel">
              <div className="admin-panel-heading"><div><span className="admin-eyebrow">ADMINISTRATION HISTORY</span><h2>Audit log</h2></div></div>
              <div className="admin-loyalty-list">{loyaltyAuditLogs.map((entry) => <article key={entry.id}><div><strong>{entry.action.replaceAll("_", " ")} · {entry.entity_type}</strong><span>{entry.admin_actor} · {new Date(entry.created_at).toLocaleString("en-KE")} · {entry.entity_id}</span>{entry.reason && <span>{entry.reason}</span>}</div></article>)}</div>
              {!loyaltyAuditLogs.length && <p className="admin-empty-state">Administrator changes will appear here.</p>}
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
