// Customer page: menu cards, a cart, placing and cancelling orders.
// Every number shown comes from the API; the cart total is only an estimate.

let menu = [];             // items from GET /menu
let cart = {};             // itemId -> quantity
let lastOrder = null;      // { key, lines } of the last order sent, for "send again"

const resultBox = document.getElementById("result");

function itemName(itemId) {
  const item = menu.find(i => i.id === itemId);
  return item ? item.name : itemId;
}

// ---------- menu ----------

async function loadMenu() {
  const r = await api("GET", "/menu", { record: false });
  menu = r.data.items;
  renderMenu();
  renderCart();
}

function stockText(item) {
  if (item.available === null) return `<span class="pill">Unlimited</span>`;
  if (item.available === 0) return `<span class="pill">Sold out</span>`;
  return `<span class="pill ${item.available <= 3 ? "warn" : "ok"}">${item.available} left</span>`;
}

function giftText(item) {
  if (item.kind !== "combo") return "";
  return item.bonusAvailable
    ? `<div class="gift ok">Bonus gift included — ${item.bonusRemaining} left</div>`
    : `<div class="gift out">Gifts have run out (combo still on sale)</div>`;
}

function renderMenu() {
  document.getElementById("menu").innerHTML = menu.map(item => {
    const soldOut = item.available === 0;
    const parts = (item.components || [])
      .map(c => `${c.qty} × ${esc(itemName(c.itemId))}`).join(" + ");
    return `
      <div class="card item-card ${soldOut ? "sold-out" : ""}">
        <div class="top">
          <h3>${esc(item.name)}</h3>
          <span class="price">$${esc(item.price)}</span>
        </div>
        <div class="row">
          ${stockText(item)}
          ${item.kind === "combo" ? `<span class="pill brand">Combo</span>` : ""}
        </div>
        <div class="facts">
          ${parts ? `<div>${parts}</div>` : ""}
          ${item.perOrderLimit ? `<div>Max ${item.perOrderLimit} per order (combos included)</div>` : ""}
        </div>
        ${giftText(item)}
        <div class="stepper">
          <button class="secondary" data-step="-1" data-item="${esc(item.id)}" ${soldOut ? "disabled" : ""}>−</button>
          <input type="number" min="0" max="50" value="${cart[item.id] || 0}"
                 data-qty="${esc(item.id)}" ${soldOut ? "disabled" : ""} aria-label="Quantity">
          <button class="secondary" data-step="1" data-item="${esc(item.id)}" ${soldOut ? "disabled" : ""}>+</button>
        </div>
      </div>`;
  }).join("");
}

// One listener for every + / − button and quantity box on the menu.
document.getElementById("menu").addEventListener("click", event => {
  const button = event.target.closest("button[data-step]");
  if (!button) return;
  setQty(button.dataset.item, (cart[button.dataset.item] || 0) + Number(button.dataset.step));
  renderMenu();
});

document.getElementById("menu").addEventListener("change", event => {
  if (event.target.dataset.qty) setQty(event.target.dataset.qty, Number(event.target.value));
});

function setQty(itemId, qty) {
  qty = Math.max(0, Math.min(50, Math.floor(qty) || 0));
  if (qty === 0) delete cart[itemId];
  else cart[itemId] = qty;
  renderCart();
}

// ---------- cart ----------

function renderCart() {
  const ids = Object.keys(cart);
  let total = 0;
  document.getElementById("cart-lines").innerHTML = ids.length === 0
    ? `<li class="muted">Your cart is empty. Use + on the menu.</li>`
    : ids.map(id => {
        const item = menu.find(i => i.id === id);
        const lineTotal = item ? Number(item.price) * cart[id] : 0;
        total += lineTotal;
        return `<li><span>${cart[id]} × ${esc(itemName(id))}</span><span>$${lineTotal.toFixed(2)}</span></li>`;
      }).join("");
  document.getElementById("cart-total").textContent = `CAD ${total.toFixed(2)}`;
  document.getElementById("place").disabled = ids.length === 0;
}

document.getElementById("clear").addEventListener("click", () => {
  cart = {};
  renderMenu();
  renderCart();
});

// ---------- placing an order ----------

document.getElementById("place").addEventListener("click", () => {
  const lines = Object.keys(cart).map(itemId => ({ itemId, qty: cart[itemId] }));
  lastOrder = { key: newIdempotencyKey(), lines };
  sendOrder();
});

// Same body, same Idempotency-Key: the server answers with the original
// result instead of placing a second order.
document.getElementById("resend").addEventListener("click", sendOrder);

async function sendOrder() {
  const buttons = ["place", "resend"].map(id => document.getElementById(id));
  buttons.forEach(b => b.disabled = true);
  const r = await api("POST", "/orders", {
    body: { lines: lastOrder.lines },
    headers: { "Idempotency-Key": lastOrder.key },
  });
  document.getElementById("last-key").textContent = `Last Idempotency-Key: ${lastOrder.key}`;
  document.getElementById("resend").disabled = false;
  if (r.ok) {
    showOrderPlaced(r.data, r.replayed);
    cart = {};
  } else {
    showAlert(resultBox, "err", errorHtml(r.data) + explain(r.data));
  }
  resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
  await Promise.all([loadMenu(), loadOrders()]);
}

function showOrderPlaced(order, replayed) {
  const gifts = order.bonus.length === 0 ? ""
    : order.bonus.every(b => b.included) ? " · Bonus gift included"
    : order.bonus.some(b => b.included) ? " · Some combos got a bonus gift; the rest ran out"
    : " · Bonus gifts have run out";
  showAlert(resultBox, "ok",
    `<strong>${replayed ? "Replayed" : "Order placed"}</strong>` +
    `${esc(order.orderId)} · ${esc(order.currency)} ${esc(order.total)}${gifts}` +
    (replayed ? ` <span class="pill warn">Replayed — no second order was placed</span>` : ""));
}

// A friendlier line for the errors a customer can cause.
function explain(data) {
  const d = (data.error && data.error.details) || {};
  if (data.error?.code === "SOLD_OUT") {
    return `<br>${esc(itemName(d.itemId))}: you asked for ${d.requested}, only ${d.available} on sale now.`;
  }
  if (data.error?.code === "PER_ORDER_LIMIT") {
    return `<br>${esc(itemName(d.itemId))}: at most ${d.limit} per order, combos included (you asked for ${d.requested}).`;
  }
  return "";
}

// ---------- my orders ----------

const STATUS_PILL = { PENDING_PAYMENT: "warn", CANCELLED: "" };

async function loadOrders() {
  const r = await api("GET", "/orders", { record: false });
  const orders = r.data.orders;
  document.getElementById("orders").innerHTML = orders.length === 0
    ? `<div class="card empty">No orders yet.</div>`
    : orders.map(orderCard).join("");
}

function orderCard(o) {
  const pending = o.status === "PENDING_PAYMENT";
  const list = items => items.length ? `<ul>${items.join("")}</ul>` : `<span class="muted">—</span>`;
  return `
    <div class="card">
      <div class="order-head">
        <div class="row">
          <span class="mono">${esc(o.orderId)}</span>
          <span class="pill ${STATUS_PILL[o.status] ?? ""}">${esc(o.status)}</span>
        </div>
        <div class="row">
          <strong>${esc(o.currency)} ${esc(o.total)}</strong>
          ${pending ? `<button class="danger small" data-cancel="${esc(o.orderId)}">Cancel</button>` : ""}
        </div>
      </div>
      <div class="order-body">
        <div><h4>Items</h4>${list(o.lines.map(l =>
          `<li>${l.qty} × ${esc(itemName(l.itemId))} <span class="muted">@ $${esc(l.unitPrice)}</span></li>`))}</div>
        <div><h4>Units taken from</h4>${list(o.claimedUnits.map(c =>
          `<li>${c.qty} × ${esc(itemName(c.itemId))} <span class="mono">${esc(c.batchId)}</span></li>`))}</div>
        <div><h4>Bonus gift</h4>${list(o.bonus.map(b =>
          `<li>${b.included ? `<span class="pill ok">Included</span>` : `<span class="pill warn">Ran out</span>`}</li>`))}</div>
        <div><h4>${pending ? "Pay by" : "Placed"}</h4>${esc(formatTime(pending ? o.paymentDueBy : o.createdAt))}</div>
      </div>
    </div>`;
}

document.getElementById("orders").addEventListener("click", async event => {
  const button = event.target.closest("button[data-cancel]");
  if (!button) return;
  const orderId = button.dataset.cancel;
  if (!confirm(`Cancel order ${orderId}? Its items and gifts go back on sale.`)) return;
  button.disabled = true;
  const r = await api("POST", `/orders/${orderId}/cancel`);
  if (r.ok) showAlert(resultBox, "ok", `<strong>Cancelled</strong>${esc(orderId)} · items and gifts are back on sale.`);
  else showAlert(resultBox, "err", errorHtml(r.data));
  await Promise.all([loadMenu(), loadOrders()]);
});

// ---------- start ----------

if (requireRole("customer")) {
  loadMenu().then(loadOrders);
}
