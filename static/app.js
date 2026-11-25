"use strict";

const $ = (id) => document.getElementById(id);
const asAdmin = location.pathname === "/admin";
const categories = ["Todos", "Bebidas", "Repostería", "Desayunos"];
const mxn = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
const money = (cents) => mxn.format(cents / 100);
const cartKey = "cafeteria-kitty-cart-v1";
const attemptKey = "cafeteria-kitty-attempt-v1";
let menu = [];
let category = "Todos";
let cart = readCart();
let ticketUrl;
let toastTimer;
let editedDish;
let deletedDish;
let checkingOut = false;

function readCart() {
  try {
    const saved = JSON.parse(localStorage.getItem(cartKey) || "{}");
    return Object.fromEntries(Object.entries(saved).filter(([id, qty]) =>
      /^\d+$/.test(id) && Number.isInteger(qty) && qty > 0 && qty <= 99));
  } catch {
    return {};
  }
}

function attemptId(items, method) {
  const fingerprint = JSON.stringify({ items, method });
  try {
    const saved = JSON.parse(localStorage.getItem(attemptKey) || "null");
    if (saved?.fingerprint === fingerprint) return saved.id;
  } catch {
    // Un valor previo incompleto se reemplaza antes de confirmar.
  }
  const id = crypto.randomUUID().replaceAll("-", "");
  localStorage.setItem(attemptKey, JSON.stringify({ fingerprint, id }));
  return id;
}

async function api(path, method = "GET", data) {
  const options = { method };
  if (data !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const error = new Error(result.error || "Ocurrió un error. Intenta de nuevo.");
    error.status = response.status;
    throw error;
  }
  return response;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(label, className, action) {
  const node = element("button", label, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function dishImage(dish) {
  const image = element("img");
  image.src = dish.image;
  image.alt = dish.name;
  image.loading = "lazy";
  return image;
}

async function loadMenu() {
  const response = await api("/api/menu");
  menu = await response.json();
  const availableIds = new Set(menu.map((dish) => String(dish.id)));
  cart = Object.fromEntries(Object.entries(cart).filter(([id]) => availableIds.has(id)));
  localStorage.setItem(cartKey, JSON.stringify(cart));
  renderCart();
  if (asAdmin) renderAdmin();
  else renderMenu();
}

function renderMenu() {
  const filters = categories.map((name) => {
    const filter = button(name, "filter", () => {
      category = name;
      renderMenu();
      $("filters").querySelector('[aria-pressed="true"]').focus();
    });
    filter.setAttribute("aria-pressed", String(name === category));
    return filter;
  });
  $("filters").replaceChildren(...filters);
  const visible = menu.filter((dish) => category === "Todos" || dish.category === category);
  $("menu-grid").replaceChildren(...visible.map((dish) => {
    const article = element("article", undefined, "card");
    const body = element("div", undefined, "card-content");
    const bottom = element("div", undefined, "card-bottom");
    const add = button("Agregar", "button small", () => {
      if (changeQuantity(dish.id, 1)) showToast(dish.name + " · En tu carrito");
    });
    add.setAttribute("aria-label", "Agregar " + dish.name);
    bottom.append(element("strong", money(dish.price)), add);
    body.append(element("h3", dish.name), element("p", dish.description), bottom);
    article.append(dishImage(dish), body);
    return article;
  }));
  if (!visible.length) $("menu-grid").append(element("p", "Aún no hay platillos en esta categoría.", "muted"));
}

function showToast(text) {
  clearTimeout(toastTimer);
  $("toast").textContent = text;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2300);
}

function changeQuantity(id, delta) {
  if (checkingOut) return false;
  const qty = (cart[id] || 0) + delta;
  if (qty > 99) {
    showToast("El límite es de 99 porciones por platillo.");
    return false;
  }
  if (qty > 0) cart[id] = qty;
  else delete cart[id];
  localStorage.setItem(cartKey, JSON.stringify(cart));
  localStorage.removeItem(attemptKey);
  $("cart-message").textContent = "";
  $("ticket-link").hidden = true;
  renderCart();
  return true;
}

function cartItems() {
  return menu.filter((dish) => cart[dish.id]).map((dish) => ({
    ...dish, quantity: cart[dish.id],
  }));
}

function renderCart() {
  const items = cartItems();
  const lines = items.map((dish) => {
    const row = element("div", undefined, "cart-row");
    const controls = element("div", undefined, "quantity");
    for (const [symbol, delta, label] of [["−", -1, "Quitar"], ["+", 1, "Agregar"]]) {
      if (delta === 1) controls.append(element("span", String(dish.quantity)));
      const control = button(symbol, "", () => {
        changeQuantity(dish.id, delta);
        const next = document.getElementById(control.id);
        (next || $("cart").querySelector(".close")).focus();
      });
      control.id = "quantity-" + dish.id + "-" + label;
      control.setAttribute("aria-label", label + " una porción de " + dish.name);
      controls.append(control);
    }
    row.append(element("h3", dish.name), controls,
      element("span", money(dish.price * dish.quantity), "muted"));
    return row;
  });
  if (!lines.length) lines.push(element("p", "Tu carrito está vacío.", "muted"));
  $("cart-items").replaceChildren(...lines);
  $("cart-count").textContent = items.reduce((sum, dish) => sum + dish.quantity, 0);
  $("cart-total").textContent = money(items.reduce((sum, dish) => sum + dish.quantity * dish.price, 0));
  $("order-summary").hidden = !items.length;
}

function renderAdmin() {
  $("admin-list").replaceChildren(...menu.map((dish) => {
    const row = element("article", undefined, "admin-row");
    const info = element("div");
    const actions = element("div", undefined, "actions");
    info.append(element("h3", dish.name),
      element("p", dish.category + " · " + money(dish.price), "muted"),
      element("p", dish.description, "muted"));
    actions.append(button("Editar", "button small outline", () => openDish(dish)),
      button("Eliminar", "button small outline", () => openDelete(dish)));
    row.append(dishImage(dish), info, actions);
    return row;
  }));
  if (!menu.length) $("admin-list").append(element("p", "Agrega el primer platillo.", "muted"));
}

function setAuthenticated(value) {
  $("login").hidden = value;
  $("manager").hidden = !value;
  $("logout").hidden = !value;
}

function openDish(dish) {
  editedDish = dish;
  const form = $("dish-form");
  form.reset();
  $("dish-message").textContent = "";
  $("dish-title").textContent = dish ? "Editar platillo" : "Agregar platillo";
  $("photo-help").textContent = dish ? "Opcional para mantener la foto actual." : "JPG, PNG o WebP. Máximo 2 MB.";
  form.elements.photo.required = !dish;
  if (dish) {
    for (const key of ["name", "category", "description"]) form.elements[key].value = dish[key];
    form.elements.price.value = (dish.price / 100).toFixed(2);
  }
  $("dish-dialog").showModal();
}

function openDelete(dish) {
  deletedDish = dish;
  $("delete-message").textContent = "";
  $("delete-description").textContent = "¿Quieres eliminar «" + dish.name + "» del menú?";
  $("delete-dialog").showModal();
}

function readPhoto(file) {
  if (!file) return Promise.resolve(null);
  if (file.size > 2 * 1024 * 1024) return Promise.reject(new Error("La foto supera los 2 MB."));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("No se pudo leer la foto."));
    reader.readAsDataURL(file);
  });
}

function handleForm(id, messageId, action) {
  $(id).addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector("button:not([type=button])");
    if (submit.disabled) return;
    submit.disabled = true;
    $(messageId).textContent = "";
    try {
      await action(form);
    } catch (error) {
      $(messageId).textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}

async function begin() {
  if (asAdmin) {
    $("customer").hidden = true;
    $("admin").hidden = false;
    $("cart-open").hidden = true;
    $("nav-admin").setAttribute("aria-current", "page");
    document.title = "Administración | Cafetería Hello Kitty";
    try {
      const response = await api("/api/session");
      setAuthenticated((await response.json()).authenticated);
    } catch (error) {
      setAuthenticated(false);
      $("login-message").textContent = error.message;
    }
  } else {
    $("nav-menu").setAttribute("aria-current", "page");
  }
  try {
    await loadMenu();
  } catch (error) {
    $(asAdmin ? "admin-message" : "menu-grid").textContent = error.message;
  }
}

document.querySelectorAll("[data-close]").forEach((node) => {
  node.addEventListener("click", () => $(node.dataset.close).close());
});
$("cart-open").addEventListener("click", () => $("cart").showModal());
$("new-dish").addEventListener("click", () => openDish(null));
$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", "POST");
    $("login-message").textContent = "";
    setAuthenticated(false);
  } catch (error) {
    $("admin-message").textContent = error.message;
  }
});
handleForm("login", "login-message", async (form) => {
  await api("/api/login", "POST", { password: form.elements.password.value });
  form.reset();
  setAuthenticated(true);
  await loadMenu();
});
handleForm("dish-form", "dish-message", async (form) => {
  const dish = editedDish;
  const fields = form.elements;
  const photo = await readPhoto(fields.photo.files[0]);
  await api(dish ? "/api/dishes/" + dish.id : "/api/dishes", dish ? "PUT" : "POST", {
    name: fields.name.value, category: fields.category.value,
    description: fields.description.value, price: Math.round(Number(fields.price.value) * 100), photo,
  });
  $("dish-dialog").close();
  $("admin-message").textContent = dish ? "Platillo actualizado." : "Platillo agregado.";
  try { await loadMenu(); }
  catch (error) { $("admin-message").textContent += " " + error.message; }
});
handleForm("delete-form", "delete-message", async () => {
  await api("/api/dishes/" + deletedDish.id, "DELETE");
  $("delete-dialog").close();
  $("admin-message").textContent = "Platillo eliminado.";
  try { await loadMenu(); }
  catch (error) { $("admin-message").textContent += " " + error.message; }
});
handleForm("checkout", "cart-message", async (form) => {
  const items = cartItems().map(({ id, quantity, price }) => ({ id, quantity, price }));
  if (!items.length) return;
  const method = form.elements.method.value;
  const order_id = attemptId(items, method);
  checkingOut = true;
  try {
    const response = await api("/api/checkout", "POST", { items, method, order_id });
    const ticket = await response.blob();
    if (ticketUrl) URL.revokeObjectURL(ticketUrl);
    ticketUrl = URL.createObjectURL(ticket);
    const link = $("ticket-link");
    link.href = ticketUrl;
    link.download = "ticket-" + order_id + ".txt";
    link.hidden = false;
    cart = {};
    localStorage.removeItem(cartKey);
    localStorage.removeItem(attemptKey);
    renderCart();
    $("cart-message").textContent = "Pedido confirmado. Tu ticket está listo.";
    link.click();
  } catch (error) {
    if (error.status === 409) await loadMenu();
    throw error;
  } finally {
    checkingOut = false;
  }
});
begin();
