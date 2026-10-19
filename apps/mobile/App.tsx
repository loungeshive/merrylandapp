import * as SecureStore from "expo-secure-store";
import { StatusBar } from "expo-status-bar";
import { useVideoPlayer, VideoView } from "expo-video";
import { useEffect, useMemo, useState } from "react";
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  FlatList,
  ImageBackground,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

const API = process.env.EXPO_PUBLIC_API_URL ?? "http://10.0.2.2:8000/api/v1";
const RATINGS_KEY = "merryland-food-ratings";
const FAVORITES_KEY = "merryland-food-favorites";

type MenuItem = {
  id: string;
  category_name: string;
  name: string;
  description: string;
  price_minor: number;
  image_url: string;
  prep_minutes: number;
};
type User = { id: string; name: string; email: string; phone: string | null };
type MenuFilter = "all" | "quick" | "drinks" | "food" | "under-500";
type OrderType = "takeaway" | "dine_in";
type CartLine = { item: MenuItem; quantity: number };

const PREVIEW_MENU: MenuItem[] = [
  {
    id: "preview-chicken",
    category_name: "Main meals",
    name: "Merryland Grilled Chicken",
    description: "Herb-marinated grilled chicken served with seasonal sides.",
    price_minor: 85000,
    image_url: "https://images.unsplash.com/photo-1532550907401-a500c9a57435?auto=format&fit=crop&w=1000&q=85",
    prep_minutes: 25,
  },
  {
    id: "preview-pilau",
    category_name: "Main meals",
    name: "Beef Pilau",
    description: "Fragrant Swahili pilau with tender beef and kachumbari.",
    price_minor: 65000,
    image_url: "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1000&q=85",
    prep_minutes: 20,
  },
  {
    id: "preview-juice",
    category_name: "Drinks",
    name: "Fresh Passion Juice",
    description: "Freshly pressed passion fruit juice.",
    price_minor: 18000,
    image_url: "https://images.unsplash.com/photo-1600271886742-f049cd451bba?auto=format&fit=crop&w=1000&q=85",
    prep_minutes: 5,
  },
];

const FILTERS: { value: MenuFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "quick", label: "Quick bites" },
  { value: "drinks", label: "Drinks" },
  { value: "food", label: "Food" },
  { value: "under-500", label: "Under KSh 500" },
];

function formatPrice(amount: number) {
  return `KSh ${(amount / 100).toLocaleString("en-KE")}`;
}

function readRatings(value: string | null): Record<string, number> {
  if (!value) return {};
  const parsed: unknown = JSON.parse(value);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
  return Object.fromEntries(
    Object.entries(parsed).filter(([, rating]) =>
      typeof rating === "number" && Number.isInteger(rating) && rating >= 1 && rating <= 5,
    ),
  );
}

function readFavorites(value: string | null): string[] {
  if (!value) return [];
  const parsed: unknown = JSON.parse(value);
  return Array.isArray(parsed) && parsed.every((id) => typeof id === "string") ? parsed : [];
}

export default function App() {
  return (
    <SafeAreaProvider>
      <MerrylandApp />
    </SafeAreaProvider>
  );
}

function MerrylandApp() {
  const insets = useSafeAreaInsets();
  const player = useVideoPlayer(require("./Camera_dives_into_glowing_tunnel_20261016141848.mp4"), (videoPlayer) => {
    videoPlayer.loop = true;
    videoPlayer.muted = true;
  });
  const [items, setItems] = useState<MenuItem[]>([]);
  const [menuUnavailable, setMenuUnavailable] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [points, setPoints] = useState(0);
  const [authMode, setAuthMode] = useState<"register" | "login">("register");
  const [showAccount, setShowAccount] = useState(false);
  const [showCart, setShowCart] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<MenuFilter>("all");
  const [showFavorites, setShowFavorites] = useState(false);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [orderType, setOrderType] = useState<OrderType>("takeaway");

  const playerItems = menuUnavailable ? PREVIEW_MENU : items;
  const visibleItems = useMemo(() => playerItems.filter((item) => {
    const isDrink = item.category_name.toLowerCase().includes("drink");
    const matchesFilter = filter === "all"
      || (filter === "quick" && item.prep_minutes <= 15)
      || (filter === "drinks" && isDrink)
      || (filter === "food" && !isDrink)
      || (filter === "under-500" && item.price_minor < 50000);
    const matchesSearch = `${item.name} ${item.description}`.toLowerCase().includes(search.trim().toLowerCase());
    return matchesFilter && matchesSearch && (!showFavorites || favorites.includes(item.id));
  }), [favorites, filter, playerItems, search, showFavorites]);
  const count = cart.reduce((sum, line) => sum + line.quantity, 0);
  const subtotal = cart.reduce((sum, line) => sum + line.item.price_minor * line.quantity, 0);

  useEffect(() => {
    player.play();
  }, [player]);

  useEffect(() => {
    void SecureStore.getItemAsync("merryland_access_token")
      .then((stored) => setToken(stored ?? ""))
      .catch(() => setError("Secure sign-in storage could not be read. Please restart the app."));
    void SecureStore.getItemAsync(RATINGS_KEY)
      .then((stored) => setRatings(readRatings(stored)))
      .catch(() => setError("Saved ratings could not be read from this device."));
    void SecureStore.getItemAsync(FAVORITES_KEY)
      .then((stored) => setFavorites(readFavorites(stored)))
      .catch(() => setError("Saved favorites could not be read from this device."));
    void fetch(`${API}/menu`)
      .then(async (response) => {
        if (!response.ok) throw new Error("The menu service is offline.");
        setItems(await response.json() as MenuItem[]);
      })
      .catch(() => setMenuUnavailable(true))
      .finally(() => setLoading(false));
  }, []);

  const addItem = (item: MenuItem) => {
    if (menuUnavailable) return;
    setCart((current) => {
      const existing = current.find((line) => line.item.id === item.id);
      return existing
        ? current.map((line) => line.item.id === item.id ? { ...line, quantity: line.quantity + 1 } : line)
        : [...current, { item, quantity: 1 }];
    });
    setNotice(`${item.name} added to your order.`);
    setError("");
  };

  const changeQuantity = (itemId: string, amount: number) => {
    setCart((current) => current.flatMap((line) => {
      if (line.item.id !== itemId) return [line];
      const quantity = line.quantity + amount;
      return quantity > 0 ? [{ ...line, quantity }] : [];
    }));
  };

  const toggleFavorite = (itemId: string) => {
    const updated = favorites.includes(itemId)
      ? favorites.filter((favorite) => favorite !== itemId)
      : [...favorites, itemId];
    setFavorites(updated);
    void SecureStore.setItemAsync(FAVORITES_KEY, JSON.stringify(updated))
      .catch(() => setError("Your favorites could not be saved on this device."));
  };

  const rateItem = (itemId: string, rating: number) => {
    const updated = { ...ratings, [itemId]: rating };
    setRatings(updated);
    void SecureStore.setItemAsync(RATINGS_KEY, JSON.stringify(updated))
      .catch(() => setError("Your rating could not be saved on this device."));
  };

  const loadPoints = async (accessToken: string) => {
    const response = await fetch(`${API}/loyalty/balance`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error("Your points balance could not be loaded.");
    const balance = await response.json();
    setPoints(balance.balance);
  };

  const submitAccount = async () => {
    setBusy(true);
    setError("");
    try {
      const payload = authMode === "register" ? { name, phone, email, password } : { email, password };
      const response = await fetch(`${API}/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Unable to sign in.");
      await SecureStore.setItemAsync("merryland_access_token", result.access_token);
      setToken(result.access_token);
      setUser(result.user);
      setShowAccount(false);
      setNotice(`Welcome${authMode === "register" ? " to Merryland" : " back"}, ${result.user.name.split(" ")[0]}.`);
      try {
        await loadPoints(result.access_token);
      } catch (cause) {
        setError(cause instanceof Error ? `Signed in, but ${cause.message.toLowerCase()}` : "Signed in, but your points balance could not be loaded.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    setBusy(true);
    try {
      await SecureStore.deleteItemAsync("merryland_access_token");
      setToken("");
      setUser(null);
      setPoints(0);
      setShowAccount(false);
      setNotice("You have been signed out.");
    } catch {
      setError("Unable to clear your saved session. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const checkout = async () => {
    if (menuUnavailable || !cart.length) return;
    if (!token) {
      setAuthMode("login");
      setShowCart(false);
      setShowAccount(true);
      setNotice("Sign in or create an account to continue with your order.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
      const orderResponse = await fetch(`${API}/orders`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          order_type: orderType,
          table_number: orderType === "dine_in" ? "1" : null,
          items: cart.map(({ item, quantity }) => ({ menu_item_id: item.id, quantity })),
        }),
      });
      const order = await orderResponse.json();
      if (!orderResponse.ok) throw new Error(order.detail ?? "Unable to create the order.");
      const paymentResponse = await fetch(`${API}/payments/${order.payment.id}/simulate-success`, {
        method: "POST",
        headers,
      });
      const confirmed = await paymentResponse.json();
      if (!paymentResponse.ok) throw new Error(confirmed.detail ?? "Payment confirmation failed.");
      setCart([]);
      setShowCart(false);
      setNotice(`Order ${confirmed.order_number} confirmed. Demo payment verified.`);
      try {
        await loadPoints(token);
      } catch {
        setError("Order confirmed, but your points balance could not be refreshed. Please reload it later.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Checkout failed. Your cart is unchanged.");
    } finally {
      setBusy(false);
    }
  };

  const openAccount = () => {
    setAuthMode(token ? "login" : "register");
    setShowAccount(true);
  };

  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <TouchableOpacity style={styles.brandWrap} onPress={() => setShowFavorites(false)} accessibilityRole="button">
          <View style={styles.brandMark}><Text style={styles.brandInitial}>M</Text></View>
          <View><Text style={styles.brand}>Merryland</Text><Text style={styles.subtitle}>KITCHEN &amp; BAR</Text></View>
        </TouchableOpacity>
        <TouchableOpacity style={styles.headerButton} onPress={openAccount}>
          <Text style={styles.headerButtonText}>{user ? `Hi, ${user.name.split(" ")[0]}` : token ? `${points} POINTS` : "Sign in"}</Text>
        </TouchableOpacity>
      </View>
      {(notice || error) ? <Text style={[styles.message, error ? styles.error : styles.notice]}>{error || notice}</Text> : null}
      <FlatList
        data={visibleItems}
        numColumns={2}
        columnWrapperStyle={styles.cardRow}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View>
            <View style={styles.hero}>
              <VideoView
                player={player}
                style={styles.heroVideo}
                contentFit="cover"
                nativeControls={false}
                accessibilityLabel="Merryland Choma Zone — great food, great moments"
              />
            </View>
            <View style={styles.menuHeading}>
              <Text style={styles.eyebrow}>FRESH FROM OUR KITCHEN</Text>
              <Text style={styles.sectionTitle}>Order your favourite food!</Text>
              <Text style={styles.sectionCaption}>Freshly made, just for you.</Text>
            </View>
            <TextInput
              style={styles.search}
              value={search}
              onChangeText={setSearch}
              placeholder="⌕  Search the menu"
              placeholderTextColor="#8b918b"
              accessibilityLabel="Search the menu"
            />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
              {FILTERS.map(({ value, label }) => (
                <TouchableOpacity key={value} style={[styles.filter, filter === value && styles.activeFilter]} onPress={() => setFilter(value)}>
                  <Text style={[styles.filterText, filter === value && styles.activeFilterText]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <View style={styles.menuTools}>
              <TouchableOpacity style={[styles.favoriteToggle, showFavorites && styles.favoriteToggleActive]} onPress={() => setShowFavorites((current) => !current)}>
                <Text style={[styles.favoriteToggleText, showFavorites && styles.favoriteToggleActiveText]}>{showFavorites ? "♥  Favorites" : "♡  Favorites"}</Text>
              </TouchableOpacity>
              <Text style={styles.itemCount}>{visibleItems.length} items</Text>
            </View>
            {menuUnavailable ? (
              <View style={styles.offlineBanner}>
                <Text style={styles.offlineTitle}>Sample menu</Text>
                <Text style={styles.offlineText}>The menu service is offline. Reconnect the API to add items and place an order.</Text>
              </View>
            ) : null}
            {loading ? <ActivityIndicator color="#d9163d" style={styles.loader} /> : null}
          </View>
        }
        renderItem={({ item }) => (
          <View style={styles.card}>
            <ImageBackground source={{ uri: item.image_url }} style={styles.foodImage} imageStyle={styles.foodImageRadius}>
              <Text style={styles.prepBadge}>◷ {item.prep_minutes} min</Text>
              {cart.some((line) => line.item.id === item.id) && !menuUnavailable ? <Text style={styles.addedBadge}>In your order</Text> : null}
              <TouchableOpacity style={styles.heartButton} onPress={() => toggleFavorite(item.id)} accessibilityLabel={`${favorites.includes(item.id) ? "Remove" : "Add"} ${item.name} ${favorites.includes(item.id) ? "from" : "to"} favorites`}>
                <Text style={[styles.heart, favorites.includes(item.id) && styles.heartSelected]}>{favorites.includes(item.id) ? "♥" : "♡"}</Text>
              </TouchableOpacity>
            </ImageBackground>
            <View style={styles.cardInfo}>
              <Text style={styles.foodName} numberOfLines={2}>{item.name}</Text>
              <Text style={styles.price}>{formatPrice(item.price_minor)}</Text>
              <Text style={styles.description} numberOfLines={2}>{item.description}</Text>
              <View style={styles.ratingRow}>
                <Text style={styles.ratingLabel}>{ratings[item.id] ? `${ratings[item.id]}.0` : "Rate"}</Text>
                <View style={styles.stars}>
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <TouchableOpacity key={rating} onPress={() => rateItem(item.id, rating)} accessibilityLabel={`${rating} star${rating === 1 ? "" : "s"}`}>
                      <Text style={[styles.star, (ratings[item.id] ?? 0) >= rating && styles.starSelected]}>★</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {ratings[item.id] ? <Text style={styles.saved}>Saved</Text> : null}
              </View>
              <TouchableOpacity style={[styles.addButton, menuUnavailable && styles.disabledButton]} onPress={() => addItem(item)} disabled={busy || menuUnavailable}>
                <Text style={styles.addText}>{menuUnavailable ? "Unavailable" : cart.some((line) => line.item.id === item.id) ? "Add another  +" : "Add to order  +"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
        ListEmptyComponent={!loading ? (
          <Text style={styles.empty}>
            {showFavorites ? "No favorites yet. Tap a heart to save a dish." : playerItems.length ? "No dishes match your search." : "No dishes are available right now."}
          </Text>
        ) : null}
        ListFooterComponent={<Text style={styles.ratingDisclaimer}>Ratings and favorites are saved on this device only.</Text>}
      />
      <View style={[styles.bottomNav, { bottom: insets.bottom + 8 }]}>
        <TouchableOpacity style={styles.navItem} onPress={() => setShowFavorites(false)}><Text style={styles.navIcon}>⌂</Text><Text style={styles.navLabel}>Home</Text></TouchableOpacity>
        <TouchableOpacity style={styles.navItem} onPress={openAccount}><Text style={styles.navIcon}>♙</Text><Text style={styles.navLabel}>Profile</Text></TouchableOpacity>
        <TouchableOpacity style={styles.navAdd} onPress={() => setShowCart(true)}><Text style={styles.navAddText}>+</Text></TouchableOpacity>
        <TouchableOpacity style={styles.navItem} onPress={() => setShowCart(true)}><Text style={styles.navIcon}>▤{count > 0 ? ` ${count}` : ""}</Text><Text style={styles.navLabel}>Order</Text></TouchableOpacity>
        <TouchableOpacity style={styles.navItem} onPress={() => setShowFavorites((current) => !current)}><Text style={styles.navIcon}>{showFavorites ? "♥" : "♡"}</Text><Text style={styles.navLabel}>Saved</Text></TouchableOpacity>
      </View>
      <Modal visible={showCart} animationType="slide" transparent onRequestClose={() => setShowCart(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeading}>
              <View><Text style={styles.eyebrow}>YOUR SELECTION</Text><Text style={styles.modalTitle}>Your order</Text></View>
              <TouchableOpacity onPress={() => setShowCart(false)}><Text style={styles.closeButton}>×</Text></TouchableOpacity>
            </View>
            <ScrollView keyboardShouldPersistTaps="handled">
              {!cart.length ? <Text style={styles.cartEmpty}>Your order is empty. Add a dish and it will appear here.</Text> : null}
              {cart.map(({ item, quantity }) => (
                <View key={item.id} style={styles.cartLine}>
                  <View style={styles.cartName}><Text style={styles.cartItemName}>{item.name}</Text><Text style={styles.cartItemPrice}>{formatPrice(item.price_minor)} each</Text></View>
                  <View style={styles.quantityControls}>
                    <TouchableOpacity style={styles.quantityButton} onPress={() => changeQuantity(item.id, -1)}><Text style={styles.quantityText}>−</Text></TouchableOpacity>
                    <Text style={styles.quantity}>{quantity}</Text>
                    <TouchableOpacity style={styles.quantityButton} onPress={() => changeQuantity(item.id, 1)}><Text style={styles.quantityText}>+</Text></TouchableOpacity>
                  </View>
                </View>
              ))}
              <Text style={styles.orderTypeLabel}>Order type</Text>
              <View style={styles.orderTypes}>
                {(["takeaway", "dine_in"] as const).map((type) => (
                  <TouchableOpacity key={type} style={[styles.orderType, orderType === type && styles.orderTypeSelected]} onPress={() => setOrderType(type)} disabled={busy}>
                    <Text style={[styles.orderTypeText, orderType === type && styles.orderTypeTextSelected]}>{type === "takeaway" ? "Takeaway" : "Dine in · Table 1"}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={styles.subtotal}><Text style={styles.subtotalLabel}>Subtotal</Text><Text style={styles.subtotalPrice}>{formatPrice(subtotal)}</Text></View>
              <Text style={styles.paymentMethod}>D  Demo payment · Payment simulation</Text>
              <TouchableOpacity style={[styles.payButton, (!cart.length || menuUnavailable) && styles.disabledButton]} onPress={() => void checkout()} disabled={busy || !cart.length || menuUnavailable}>
                <Text style={styles.payButtonText}>{busy ? "Processing…" : `Pay ${formatPrice(subtotal)}  →`}</Text>
              </TouchableOpacity>
              <Text style={styles.disclaimer}>Local demo payment only. Live M-Pesa is not connected.</Text>
            </ScrollView>
          </View>
        </View>
      </Modal>
      <Modal visible={showAccount} animationType="slide" transparent onRequestClose={() => setShowAccount(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeading}>
              <View><Text style={styles.eyebrow}>{token ? "YOUR ACCOUNT" : authMode === "register" ? "JOIN MERRYLAND" : "WELCOME BACK"}</Text><Text style={styles.modalTitle}>{token ? user?.name ?? "Merryland Rewards" : authMode === "register" ? "Create your account" : "Sign in to Merryland"}</Text></View>
              <TouchableOpacity onPress={() => setShowAccount(false)}><Text style={styles.closeButton}>×</Text></TouchableOpacity>
            </View>
            {token ? (
              <View>
                <Text style={styles.accountPoints}>{points} loyalty points</Text>
                <Text style={styles.description}>Your session is stored securely on this device. Local development payments only; live M-Pesa is not connected yet.</Text>
                <TouchableOpacity style={styles.payButton} onPress={() => void signOut()} disabled={busy}><Text style={styles.payButtonText}>{busy ? "Please wait…" : "Sign out"}</Text></TouchableOpacity>
              </View>
            ) : (
              <ScrollView keyboardShouldPersistTaps="handled">
                {authMode === "register" ? <TextInput style={styles.field} value={name} onChangeText={setName} placeholder="Your name" autoComplete="name" /> : null}
                {authMode === "register" ? <TextInput style={styles.field} value={phone} onChangeText={setPhone} placeholder="Phone number" keyboardType="phone-pad" /> : null}
                <TextInput style={styles.field} value={email} onChangeText={setEmail} placeholder="Email address" autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
                <TextInput style={styles.field} value={password} onChangeText={setPassword} placeholder={authMode === "register" ? "Password (10+ characters)" : "Password"} secureTextEntry />
                <TouchableOpacity style={styles.payButton} onPress={() => void submitAccount()} disabled={busy}>
                  <Text style={styles.payButtonText}>{busy ? "Please wait…" : authMode === "register" ? "Create account" : "Sign in"}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setAuthMode(authMode === "register" ? "login" : "register")}>
                  <Text style={styles.switchMode}>{authMode === "register" ? "Already a member? Sign in" : "New here? Create an account"}</Text>
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f6f7f5" },
  header: { minHeight: 68, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#fff", borderBottomWidth: 1, borderBottomColor: "#e8ece7" },
  brandWrap: { flexDirection: "row", alignItems: "center", gap: 9 },
  brandMark: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: "#d9163d" },
  brandInitial: { color: "#fff", fontFamily: "Georgia", fontStyle: "italic", fontSize: 23 },
  brand: { color: "#d9163d", fontFamily: "Georgia", fontSize: 18, fontWeight: "700" },
  subtitle: { color: "#818780", fontSize: 7, letterSpacing: 1.6, marginTop: 2 },
  headerButton: { paddingVertical: 9, paddingHorizontal: 12, backgroundColor: "#fff0f2", borderRadius: 7 },
  headerButtonText: { color: "#b91334", fontSize: 11, fontWeight: "700" },
  message: { marginHorizontal: 14, marginTop: 9, padding: 10, borderRadius: 7, fontSize: 12, lineHeight: 18 },
  error: { color: "#873f30", backgroundColor: "#faeae6" },
  notice: { color: "#b91334", backgroundColor: "#fff0f2" },
  content: { paddingHorizontal: 14, paddingTop: 12, paddingBottom: 88 },
  hero: { width: "100%", aspectRatio: 16 / 9, overflow: "hidden", borderRadius: 12, backgroundColor: "#e6e8e0" },
  heroVideo: { width: "100%", height: "100%" },
  menuHeading: { marginTop: 20, marginBottom: 14 },
  eyebrow: { color: "#a17a48", fontSize: 9, fontWeight: "700", letterSpacing: 1.6 },
  sectionTitle: { marginTop: 7, color: "#d9163d", fontFamily: "Georgia", fontSize: 26, lineHeight: 31 },
  sectionCaption: { marginTop: 4, color: "#818780", fontSize: 12 },
  search: { minHeight: 42, paddingHorizontal: 13, borderWidth: 1, borderColor: "#e8ece7", borderRadius: 8, backgroundColor: "#fff", color: "#242a25", fontSize: 13 },
  filters: { gap: 7, paddingVertical: 13 },
  filter: { paddingVertical: 9, paddingHorizontal: 13, borderRadius: 20, backgroundColor: "#fff" },
  activeFilter: { backgroundColor: "#d9163d" },
  filterText: { color: "#737b73", fontSize: 11, fontWeight: "600" },
  activeFilterText: { color: "#fff" },
  menuTools: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  favoriteToggle: { paddingVertical: 7, paddingHorizontal: 11, borderRadius: 18, backgroundColor: "#fff" },
  favoriteToggleActive: { backgroundColor: "#fff0f2" },
  favoriteToggleText: { color: "#777d77", fontSize: 11, fontWeight: "600" },
  favoriteToggleActiveText: { color: "#d9163d" },
  itemCount: { color: "#939a92", fontSize: 10 },
  offlineBanner: { marginBottom: 13, padding: 11, borderWidth: 1, borderColor: "#f0dfbd", borderRadius: 8, backgroundColor: "#fff9ed" },
  offlineTitle: { color: "#755925", fontSize: 12, fontWeight: "700" },
  offlineText: { marginTop: 4, color: "#755925", fontSize: 11, lineHeight: 16 },
  loader: { marginVertical: 18 },
  cardRow: { justifyContent: "space-between", gap: 11, marginBottom: 11 },
  card: { flex: 1, overflow: "hidden", borderRadius: 12, backgroundColor: "#fff", borderWidth: 1, borderColor: "#e9ede8" },
  foodImage: { aspectRatio: 1 / 0.9, justifyContent: "space-between", backgroundColor: "#e4e6df" },
  foodImageRadius: { resizeMode: "cover" },
  prepBadge: { alignSelf: "flex-start", margin: 7, paddingVertical: 5, paddingHorizontal: 7, overflow: "hidden", borderRadius: 4, backgroundColor: "rgba(255,255,255,0.94)", color: "#454e45", fontSize: 8, fontWeight: "700" },
  addedBadge: { position: "absolute", top: 7, right: 7, padding: 5, borderRadius: 4, backgroundColor: "#d9163d", color: "#fff", fontSize: 7, fontWeight: "700" },
  heartButton: { position: "absolute", right: 7, bottom: 7, width: 29, height: 29, alignItems: "center", justifyContent: "center", borderRadius: 15, backgroundColor: "rgba(255,255,255,0.94)" },
  heart: { color: "#777d77", fontSize: 16 },
  heartSelected: { color: "#d9163d" },
  cardInfo: { padding: 9 },
  foodName: { minHeight: 32, color: "#242a25", fontFamily: "Georgia", fontSize: 13, fontWeight: "600", lineHeight: 16 },
  price: { marginTop: 4, color: "#d9163d", fontSize: 11, fontWeight: "700" },
  description: { marginTop: 5, color: "#818780", fontSize: 10, lineHeight: 14 },
  ratingRow: { minHeight: 22, flexDirection: "row", alignItems: "center", gap: 3, marginTop: 5 },
  ratingLabel: { color: "#8a9189", fontSize: 8 },
  stars: { flexDirection: "row", alignItems: "center" },
  star: { color: "#c9ccc7", fontSize: 12, paddingHorizontal: 1 },
  starSelected: { color: "#d39a35" },
  saved: { color: "#818780", fontSize: 7 },
  addButton: { minHeight: 32, marginTop: 2, paddingVertical: 7, paddingHorizontal: 8, alignItems: "center", justifyContent: "center", borderRadius: 7, backgroundColor: "#fff0f2" },
  disabledButton: { opacity: 0.55 },
  addText: { color: "#d9163d", fontSize: 9, fontWeight: "700" },
  empty: { padding: 24, color: "#777d77", textAlign: "center", fontSize: 12, lineHeight: 18 },
  ratingDisclaimer: { marginTop: 13, marginBottom: 8, color: "#8a9189", textAlign: "center", fontSize: 9 },
  bottomNav: { position: "absolute", zIndex: 20, right: 0, bottom: 0, left: 0, height: 68, flexDirection: "row", alignItems: "center", justifyContent: "space-around", backgroundColor: "#d9163d", paddingHorizontal: 7, paddingBottom: 8, elevation: 12 },
  navItem: { flex: 1, alignItems: "center", justifyContent: "center", gap: 2 },
  navIcon: { color: "#fff", fontSize: 17 },
  navLabel: { color: "rgba(255,255,255,0.84)", fontSize: 8 },
  navAdd: { width: 44, height: 44, marginTop: -19, alignItems: "center", justifyContent: "center", borderWidth: 4, borderColor: "#f6f7f5", borderRadius: 24, backgroundColor: "#d9163d" },
  navAddText: { color: "#fff", fontSize: 27, lineHeight: 32 },
  modalBackdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(20,25,20,0.42)" },
  modalSheet: { maxHeight: "88%", padding: 20, paddingBottom: 30, borderTopLeftRadius: 18, borderTopRightRadius: 18, backgroundColor: "#fff" },
  modalHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  modalTitle: { marginTop: 5, color: "#242a25", fontFamily: "Georgia", fontSize: 24 },
  closeButton: { color: "#777d77", fontSize: 32, lineHeight: 34, paddingHorizontal: 5 },
  cartEmpty: { paddingVertical: 26, color: "#818780", textAlign: "center", fontSize: 13 },
  cartLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "#e8ece7" },
  cartName: { flex: 1 },
  cartItemName: { color: "#242a25", fontSize: 13, fontWeight: "600" },
  cartItemPrice: { marginTop: 4, color: "#818780", fontSize: 10 },
  quantityControls: { flexDirection: "row", alignItems: "center", gap: 11 },
  quantityButton: { width: 28, height: 28, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: "#fff0f2" },
  quantityText: { color: "#d9163d", fontSize: 18, lineHeight: 21 },
  quantity: { minWidth: 12, color: "#242a25", textAlign: "center", fontSize: 12, fontWeight: "700" },
  orderTypeLabel: { marginTop: 18, marginBottom: 8, color: "#454e45", fontSize: 11, fontWeight: "700" },
  orderTypes: { flexDirection: "row", gap: 8 },
  orderType: { flex: 1, paddingVertical: 11, alignItems: "center", borderWidth: 1, borderColor: "#e8ece7", borderRadius: 8 },
  orderTypeSelected: { borderColor: "#d9163d", backgroundColor: "#fff0f2" },
  orderTypeText: { color: "#737b73", fontSize: 10 },
  orderTypeTextSelected: { color: "#b91334", fontWeight: "700" },
  subtotal: { flexDirection: "row", justifyContent: "space-between", marginTop: 19, paddingTop: 14, borderTopWidth: 1, borderTopColor: "#e8ece7" },
  subtotalLabel: { color: "#737b73", fontSize: 12 },
  subtotalPrice: { color: "#242a25", fontSize: 14, fontWeight: "700" },
  paymentMethod: { marginTop: 16, marginBottom: 13, color: "#737b73", fontSize: 11 },
  payButton: { minHeight: 46, alignItems: "center", justifyContent: "center", borderRadius: 8, backgroundColor: "#d9163d" },
  payButtonText: { color: "#fff", fontSize: 13, fontWeight: "700" },
  disclaimer: { marginTop: 10, color: "#8a9189", textAlign: "center", fontSize: 9, lineHeight: 14 },
  accountPoints: { marginBottom: 8, color: "#d9163d", fontSize: 14, fontWeight: "700" },
  field: { minHeight: 46, marginVertical: 5, paddingHorizontal: 12, borderWidth: 1, borderColor: "#dcd6ca", borderRadius: 7, backgroundColor: "#fff", color: "#242a25", fontSize: 13 },
  switchMode: { paddingVertical: 15, color: "#b91334", textAlign: "center", fontSize: 12, fontWeight: "600" },
});
