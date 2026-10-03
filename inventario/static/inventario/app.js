"use strict";

const state = {
  access: localStorage.getItem("nexo_access"),
  refresh: localStorage.getItem("nexo_refresh"),
  username: localStorage.getItem("nexo_username") || "",
  role: localStorage.getItem("nexo_role") || "",
  products: [],
  categories: [],
  cart: [],
  orders: [],
  view: "catalog",
};

const $ = (selector) => document.querySelector(selector);
const money = (value) => "$" + Number(value || 0).toLocaleString("es-CL", { maximumFractionDigits: 0 });
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
let toastTimer;

// Todas las solicitudes autenticadas usan el access token y renuevan la sesion una vez.
async function api(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {});
  if (state.access) headers.set("Authorization", `Bearer ${state.access}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response = await fetch(path, { ...options, headers });
  if (response.status === 401 && retry && state.refresh && !path.includes("/api/token/")) {
    const refreshed = await fetch("/api/token/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: state.refresh }),
    });
    if (refreshed.ok) {
      const tokens = await refreshed.json();
      state.access = tokens.access;
      localStorage.setItem("nexo_access", state.access);
      return api(path, options, false);
    }
    signOut(false);
  }
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || Object.values(payload).flat().join(" ") || "No fue posible completar la solicitud.";
    throw new Error(Array.isArray(detail) ? detail.join(" ") : String(detail));
  }
  return payload;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

function openDialog(id) { $("#" + id).showModal(); }
function closeDialog(id) { $("#" + id).close(); }
function resultsOf(payload) { return Array.isArray(payload) ? payload : payload.results || []; }
function displayDate(value) { return new Date(`${value}T12:00:00`).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" }); }
function activeOrders() { return state.orders.filter((order) => !["ENTREGADO", "CANCELADO"].includes(order.status)); }
function cartTotal() { return state.cart.reduce((sum, row) => sum + Number(row.product.unit_price) * row.quantity, 0); }

// El servidor decide el rol; la interfaz solo adapta las acciones disponibles.
function renderHeader() {
  const manager = state.role === "gestor_bodega";
  const authenticated = Boolean(state.access && state.username);
  $("#account-name").textContent = authenticated ? state.username : "Visitante";
  $("#account-role").textContent = manager ? "Gestor de bodega" : authenticated ? "Institución médica" : "Catálogo público";
  $("#avatar").textContent = authenticated ? state.username.slice(0, 2).toUpperCase() : "NS";
  $("#session-label").textContent = authenticated ? (manager ? "Bodega farmacéutica" : "Clínica Norte") : "Sesión no iniciada";
  $("#auth-button").textContent = authenticated ? "Cerrar sesión" : "Iniciar sesión";
  $("#add-product-button").hidden = !manager || state.view !== "catalog";
  $("#metrics").hidden = state.view === "orders";
  $("#catalog-view").hidden = state.view !== "catalog";
  $("#orders-view").hidden = state.view !== "orders";
  $("#breadcrumb-current").textContent = state.view === "orders" ? "Solicitudes" : "Catálogo";
  $("#page-eyebrow").textContent = manager ? "Operaciones · Bodega farmacéutica" : authenticated ? "Abastecimiento · Clínica Norte" : "Catálogo institucional";
  $("#page-title").textContent = state.view === "orders" ? (manager ? "Solicitudes recibidas" : "Mis solicitudes") : manager ? "Inventario de bodega" : "Insumos disponibles";
  $("#page-subtitle").textContent = state.view === "orders" ? "Consulta el estado y gestiona el despacho de cada solicitud." : manager ? "Existencias por lote, vencimiento y precio por caja." : "Suministros clínicos verificados, listos para tu próxima solicitud.";
  $("#cart-fab").hidden = manager || !authenticated || state.cart.length === 0;
  $("#order-count").hidden = !authenticated || state.orders.length === 0;
  $("#order-count").textContent = String(activeOrders().length);
  document.querySelectorAll(".nav [data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
    if (button.classList.contains("active")) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function renderMetrics() {
  const today = new Date();
  const expiryLimit = new Date(today.getTime() + 90 * 86400000);
  $("#metric-products").textContent = String(state.products.length);
  $("#metric-orders").textContent = String(activeOrders().length);
  $("#metric-low").textContent = String(state.products.filter((product) => product.stock > 0 && product.stock < 15).length);
  $("#metric-expiry").textContent = String(state.products.filter((product) => {
    const expiry = new Date(`${product.expiry_date}T00:00:00`);
    return expiry >= today && expiry <= expiryLimit;
  }).length);
}

function renderCategories() {
  const selected = $("#category-filter").value;
  const options = state.categories.map((category) => `<option value="${escapeHtml(category.slug)}">${escapeHtml(category.name)}</option>`).join("");
  $("#category-filter").innerHTML = `<option value="">Todas las categorías</option>${options}`;
  $("#category-filter").value = selected;
  $("#product-category").innerHTML = state.categories.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join("");
}

function renderCatalog() {
  const body = $("#product-rows");
  const manager = state.role === "gestor_bodega";
  $("#results-label").textContent = `${state.products.length} ${state.products.length === 1 ? "insumo" : "insumos"}`;
  if (!state.products.length) {
    body.innerHTML = `<tr><td colspan="7" class="empty-state">${manager ? "Aún no hay insumos en el inventario." : "No encontramos insumos con esos filtros."}</td></tr>`;
    renderMetrics();
    return;
  }
  body.innerHTML = state.products.map((product) => {
    const expiredSoon = (new Date(`${product.expiry_date}T00:00:00`) - new Date()) / 86400000 <= 90;
    const stockClass = product.stock === 0 ? "out" : product.stock < 15 ? "low" : "";
    const action = manager
      ? `<div class="manager-actions"><button class="table-action" data-edit="${product.id}" aria-label="Editar ${escapeHtml(product.name)}" title="Editar">✎</button><button class="table-action" data-delete="${product.id}" aria-label="Retirar ${escapeHtml(product.name)}" title="Retirar del catálogo">×</button></div>`
      : `<button class="table-action" data-add="${product.id}" aria-label="Agregar ${escapeHtml(product.name)}" title="Agregar al carro" ${product.stock === 0 ? "disabled" : ""}>+</button>`;
    const icon = product.category_name === "Equipamiento" ? "◇" : product.category_name === "Medicamentos" ? "⌑" : "▱";
    const iconClass = product.category_name === "Medicamentos" ? "orange" : "";
    return `<tr><td><div class="product-name"><span class="product-icon ${iconClass}" aria-hidden="true">${icon}</span><span><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.active_ingredient)}</small></span></div></td><td><span class="category-tag">${escapeHtml(product.category_name)}</span></td><td>${escapeHtml(product.lot)}</td><td class="expiry ${expiredSoon ? "soon" : ""}">${displayDate(product.expiry_date)}</td><td><span class="stock"><i class="stock-dot ${stockClass}"></i>${product.stock ? `${product.stock} cajas` : "Agotado"}</span></td><td class="price">${money(product.unit_price)}</td><td>${action}</td></tr>`;
  }).join("");
  renderMetrics();
}

async function refreshCatalog() {
  const params = new URLSearchParams();
  const search = $("#search-input").value.trim();
  if (search) params.set("search", search);
  if ($("#category-filter").value) params.set("category", $("#category-filter").value);
  if ($("#stock-filter").value) params.set("available", $("#stock-filter").value);
  const query = params.size ? `?${params}` : "";
  try {
    state.products = resultsOf(await api(`/api/insumos/${query}`));
    renderCatalog();
  } catch (error) {
    $("#product-rows").innerHTML = `<tr><td colspan="7" class="empty-state">No se pudo cargar el catálogo: ${escapeHtml(error.message)}</td></tr>`;
  }
}

function renderCart() {
  const units = state.cart.reduce((sum, row) => sum + row.quantity, 0);
  $("#cart-count").textContent = `${units} ${units === 1 ? "caja" : "cajas"}`;
  $("#cart-total").textContent = money(cartTotal());
  $("#cart-fab").hidden = state.role === "gestor_bodega" || !state.access || units === 0;
  $("#checkout-button").disabled = state.cart.length === 0;
  $("#clear-cart-button").disabled = state.cart.length === 0;
  if (!state.cart.length) {
    $("#cart-body").innerHTML = `<div class="empty-state">Tu solicitud está vacía.</div>`;
    return;
  }
  $("#cart-body").innerHTML = state.cart.map((row) => `<div class="cart-line"><div><strong>${escapeHtml(row.product.name)}</strong><small>${money(row.product.unit_price)} por caja · ${row.product.stock} disponibles</small></div><div class="qty-control"><button data-quantity="-1" data-row="${row.id}" aria-label="Quitar una caja">−</button><span>${row.quantity}</span><button data-quantity="1" data-row="${row.id}" aria-label="Agregar una caja" ${row.quantity >= row.product.stock ? "disabled" : ""}>+</button></div><div class="cart-line-total">${money(Number(row.product.unit_price) * row.quantity)}</div></div>`).join("") + `<div class="cart-total"><span>Total de la solicitud</span><strong>${money(cartTotal())}</strong></div>`;
}

async function refreshCart() {
  if (!state.access || state.role !== "institucion_medica") { state.cart = []; renderCart(); renderHeader(); return; }
  state.cart = await api("/api/carro-insumos/");
  renderCart();
  renderHeader();
}

function statusLabel(status) {
  return ({ PAGADO: "PAGADO", EN_PREPARACION: "EN PREPARACIÓN", EN_DESPACHO: "EN DESPACHO", ENTREGADO: "ENTREGADO", CANCELADO: "CANCELADO" })[status] || status;
}

function renderOrders() {
  const list = $("#orders-list");
  if (!state.orders.length) {
    list.innerHTML = `<div class="empty-state">${state.role === "gestor_bodega" ? "Aún no hay solicitudes recibidas." : "Todavía no tienes solicitudes."}</div>`;
    return;
  }
  list.innerHTML = state.orders.map((order) => {
    const statusClass = order.status === "CANCELADO" ? "cancelled" : ["PAGADO", "EN_PREPARACION"].includes(order.status) ? "pending" : "";
    const terminal = ["ENTREGADO", "CANCELADO"].includes(order.status);
    const action = state.role === "gestor_bodega" && !terminal
      ? `<button class="secondary-button" data-update-order="${order.id}">Actualizar estado</button>`
      : `<span class="status ${statusClass}">${escapeHtml(statusLabel(order.status))}</span>`;
    const details = order.items.map((item) => `${item.quantity} × ${escapeHtml(item.product_name)}`).join(", ");
    return `<article class="order-row"><div><strong>${escapeHtml(order.id.slice(0, 13))}</strong><small>${displayDate(order.created_at.slice(0, 10))}</small></div><div><strong>${state.role === "gestor_bodega" ? escapeHtml(order.username) : "Solicitud institucional"}</strong><small>${details}</small></div><div><strong>${order.items.reduce((sum, item) => sum + item.quantity, 0)} cajas</strong></div><div><strong>${money(order.total)}</strong></div><div>${action}</div></article>`;
  }).join("");
}

async function refreshOrders() {
  if (!state.access) { state.orders = []; renderOrders(); return; }
  const path = state.role === "gestor_bodega" ? "/api/solicitudes/" : "/api/mis-solicitudes/";
  state.orders = resultsOf(await api(path));
  renderOrders();
  renderMetrics();
  renderHeader();
}

async function loadAll() {
  try {
    const [categories, products] = await Promise.all([api("/api/categorias/"), api("/api/insumos/")]);
    state.categories = resultsOf(categories);
    state.products = resultsOf(products);
    renderCategories();
    renderCatalog();
    if (state.access) {
      await Promise.all([refreshOrders(), state.role === "institucion_medica" ? refreshCart() : Promise.resolve()]);
    } else {
      state.cart = [];
      state.orders = [];
      renderOrders();
      renderCart();
    }
    renderHeader();
  } catch (error) {
    showToast(error.message);
  }
}

async function addToCart(productId) {
  if (!state.access) { openDialog("auth-dialog"); return showToast("Inicia sesión para agregar insumos."); }
  if (state.role !== "institucion_medica") return showToast("El carro está disponible para instituciones médicas.");
  try {
    await api("/api/carro-insumos/", { method: "POST", body: JSON.stringify({ product_id: productId, quantity: 1 }) });
    await refreshCart();
    showToast("Insumo agregado al carro persistente.");
  } catch (error) { showToast(error.message); }
}

async function changeQuantity(rowId, difference) {
  const row = state.cart.find((item) => String(item.id) === String(rowId));
  if (!row) return;
  try {
    if (row.quantity + difference < 1) await api(`/api/carro-insumos/${row.id}/`, { method: "DELETE" });
    else await api(`/api/carro-insumos/${row.id}/`, { method: "PATCH", body: JSON.stringify({ quantity: row.quantity + difference }) });
    await refreshCart();
  } catch (error) { showToast(error.message); }
}

async function checkout() {
  try {
    const order = await api("/api/solicitudes/confirmar/", { method: "POST", body: JSON.stringify({}) });
    closeDialog("cart-dialog");
    state.view = "orders";
    await Promise.all([refreshCatalog(), refreshOrders(), refreshCart()]);
    renderHeader();
    showToast(`Solicitud ${order.id.slice(0, 13)} confirmada y pagada.`);
  } catch (error) {
    await refreshCatalog();
    await refreshCart();
    showToast(error.message);
  }
}

async function saveProduct(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  const id = values.id;
  delete values.id;
  values.category = Number(values.category);
  values.unit_price = Number(values.unit_price);
  values.stock = Number(values.stock);
  const url = id ? `/api/insumos/${id}/` : "/api/insumos/";
  try {
    await api(url, { method: id ? "PUT" : "POST", body: JSON.stringify(values) });
    closeDialog("product-dialog");
    await refreshCatalog();
    showToast(id ? "Insumo actualizado." : "Insumo agregado al inventario.");
  } catch (error) { showToast(error.message); }
}

function editProduct(id) {
  const product = state.products.find((item) => String(item.id) === String(id));
  if (!product) return;
  const form = $("#product-form");
  form.elements.id.value = product.id;
  form.elements.name.value = product.name;
  form.elements.active_ingredient.value = product.active_ingredient;
  form.elements.category.value = product.category;
  form.elements.lot.value = product.lot;
  form.elements.expiry_date.value = product.expiry_date;
  form.elements.unit_price.value = product.unit_price;
  form.elements.stock.value = product.stock;
  $("#product-dialog-title").textContent = "Editar insumo";
  openDialog("product-dialog");
}

async function removeProduct(id) {
  const product = state.products.find((item) => String(item.id) === String(id));
  if (!product || !confirm(`¿Retirar ${product.name} del catálogo?`)) return;
  try {
    await api(`/api/insumos/${id}/`, { method: "DELETE" });
    await refreshCatalog();
    showToast("Insumo retirado del catálogo.");
  } catch (error) { showToast(error.message); }
}

function openStatusDialog(id) {
  const order = state.orders.find((item) => item.id === id);
  if (!order) return;
  const next = ({ PAGADO: ["EN_PREPARACION", "CANCELADO"], EN_PREPARACION: ["EN_DESPACHO", "CANCELADO"], EN_DESPACHO: ["ENTREGADO", "CANCELADO"] })[order.status] || [];
  $("#status-order-label").textContent = `${order.id} · estado actual: ${statusLabel(order.status)}`;
  $("#status-form").elements.id.value = order.id;
  $("#new-status").innerHTML = next.map((value) => `<option value="${value}">${statusLabel(value)}</option>`).join("");
  openDialog("status-dialog");
}

async function updateOrderStatus(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api(`/api/solicitudes/${form.elements.id.value}/estado/`, {
      method: "PATCH",
      body: JSON.stringify({ status: form.elements.status.value }),
    });
    closeDialog("status-dialog");
    await Promise.all([refreshOrders(), refreshCatalog()]);
    showToast("Estado de la solicitud actualizado.");
  } catch (error) { showToast(error.message); }
}

function setAuthMode(mode) {
  const registering = mode === "register";
  $("#login-form").hidden = registering;
  $("#register-form").hidden = !registering;
  document.querySelectorAll("[data-auth-mode]").forEach((button) => button.classList.toggle("active", button.dataset.authMode === mode));
  $("#auth-title").textContent = registering ? "Crear cuenta institucional" : "Accede a Nexo Salud";
  $("#auth-subtitle").textContent = registering ? "Registra tu institución para enviar solicitudes." : "Tu cuenta institucional para solicitar insumos.";
}

async function signIn(username, password) {
  const tokens = await api("/api/token/", { method: "POST", body: JSON.stringify({ username, password }) }, false);
  state.access = tokens.access;
  state.refresh = tokens.refresh;
  state.username = tokens.username;
  state.role = tokens.role;
  localStorage.setItem("nexo_access", tokens.access);
  localStorage.setItem("nexo_refresh", tokens.refresh);
  localStorage.setItem("nexo_username", tokens.username);
  localStorage.setItem("nexo_role", tokens.role);
}

function signOut(showMessage = true) {
  state.access = null;
  state.refresh = null;
  state.username = "";
  state.role = "";
  state.cart = [];
  state.orders = [];
  ["nexo_access", "nexo_refresh", "nexo_username", "nexo_role"].forEach((key) => localStorage.removeItem(key));
  renderHeader();
  renderCart();
  renderOrders();
  if (showMessage) showToast("Sesión cerrada. El carro sigue guardado en tu cuenta.");
}

// Los formularios cambian el modo de auth; solo el servidor asigna y firma los roles.
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#login-error").textContent = "";
  try {
    await signIn(form.elements.username.value, form.elements.password.value);
    closeDialog("auth-dialog");
    form.reset();
    await loadAll();
    showToast("Sesión iniciada.");
  } catch (error) { $("#login-error").textContent = error.message; }
});

$("#register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  $("#register-error").textContent = "";
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    await api("/api/auth/registro/", { method: "POST", body: JSON.stringify(payload) }, false);
    await signIn(payload.username, payload.password);
    closeDialog("auth-dialog");
    form.reset();
    setAuthMode("login");
    await loadAll();
    showToast("Cuenta institucional creada.");
  } catch (error) { $("#register-error").textContent = error.message; }
});

$("#auth-button").addEventListener("click", () => {
  if (state.access) return signOut();
  setAuthMode("login");
  openDialog("auth-dialog");
});
document.querySelectorAll("[data-auth-mode]").forEach((button) => button.addEventListener("click", () => setAuthMode(button.dataset.authMode)));
document.querySelectorAll(".nav [data-view]").forEach((button) => button.addEventListener("click", async () => {
  if (button.dataset.view === "orders" && !state.access) { openDialog("auth-dialog"); return showToast("Inicia sesión para consultar solicitudes."); }
  state.view = button.dataset.view;
  renderHeader();
  if (state.view === "orders") await refreshOrders();
}));
$("#search-input").addEventListener("input", () => { clearTimeout(window.catalogSearchTimer); window.catalogSearchTimer = setTimeout(refreshCatalog, 250); });
$("#category-filter").addEventListener("change", refreshCatalog);
$("#stock-filter").addEventListener("change", refreshCatalog);
$("#product-rows").addEventListener("click", (event) => {
  const add = event.target.closest("[data-add]");
  const edit = event.target.closest("[data-edit]");
  const remove = event.target.closest("[data-delete]");
  if (add) addToCart(add.dataset.add);
  if (edit) editProduct(edit.dataset.edit);
  if (remove) removeProduct(remove.dataset.delete);
});
$("#orders-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-update-order]");
  if (button) openStatusDialog(button.dataset.updateOrder);
});
$("#cart-fab").addEventListener("click", async () => { await refreshCart(); renderCart(); openDialog("cart-dialog"); });
$("#cart-body").addEventListener("click", (event) => {
  const button = event.target.closest("[data-quantity]");
  if (button) changeQuantity(button.dataset.row, Number(button.dataset.quantity));
});
$("#checkout-button").addEventListener("click", checkout);
$("#clear-cart-button").addEventListener("click", async () => {
  try { await api("/api/carro-insumos/", { method: "DELETE" }); await refreshCart(); }
  catch (error) { showToast(error.message); }
});
$("#add-product-button").addEventListener("click", () => {
  const form = $("#product-form");
  form.reset();
  form.elements.id.value = "";
  $("#product-dialog-title").textContent = "Nuevo insumo";
  openDialog("product-dialog");
});
$("#product-form").addEventListener("submit", saveProduct);
$("#status-form").addEventListener("submit", updateOrderStatus);
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeDialog(button.dataset.close)));
document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); }));

renderHeader();
renderCart();
renderOrders();
loadAll();