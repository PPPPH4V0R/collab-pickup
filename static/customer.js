// Customer site: menu, cart, placing and cancelling orders.

let menu = [];             // items from GET /menu
let cart = {};             // itemId -> quantity

const resultBox = document.getElementById("result");

function itemName(itemId) {
  const item = menu.find(i => i.id === itemId);
  return item ? item.name : itemId;
}

// ---------- menu ----------

async function loadMenu() {
  const r = await api("GET", "/menu");
  menu = r.data.items;
  renderMenu();
  renderCart();
}

function stockText(item) {
  if (item.available === null) return "";
  if (item.available === 0) return `<span class="pill">Sold out</span>`;
  return `<span class="pill ${item.available <= 3 ? "warn" : "ok"}">${item.available} left</span>`;
}

function giftText(item) {
  if (item.kind !== "combo") return "";
  return item.bonusAvailable
    ? `<div class="gift ok">Comes with a bonus gift</div>`
    : `<div class="gift out">Bonus gifts have run out</div>`;
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
        <div class="row">${stockText(item)}</div>
        ${parts ? `<div class="facts">${parts}</div>` : ""}
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
    ? `<li class="muted">Your cart is empty.</li>`
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

// Every order gets a fresh Idempotency-Key, so a network retry of the same
// request can never place it twice.
document.getElementById("place").addEventListener("click", async () => {
  const button = document.getElementById("place");
  button.disabled = true;
  const lines = Object.keys(cart).map(itemId => ({ itemId, qty: cart[itemId] }));
  const r = await api("POST", "/orders", {
    body: { lines },
    headers: { "Idempotency-Key": newIdempotencyKey() },
  });
  if (r.ok) {
    const o = r.data;
    const gift = o.bonus.length === 0 ? "" : o.bonus.some(b => b.included)
      ? " Bonus gift included." : " Bonus gifts have run out.";
    showAlert(resultBox, "ok", `Order placed: ${o.currency} ${o.total}.${gift}`);
    cart = {};
  } else {
    showAlert(resultBox, "err", orderErrorText(r.data));
  }
  resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
  await Promise.all([loadMenu(), loadOrders()]);
});

// One sentence for the customer. For "sold out" and "too many" the item's
// name makes the server's message clearer.
function orderErrorText(data) {
  const e = data.error || {};
  const d = e.details || {};
  if (e.code === "SOLD_OUT") {
    return d.available === 0
      ? `${itemName(d.itemId)} is sold out right now.`
      : `Only ${d.available} ${itemName(d.itemId)} left.`;
  }
  if (e.code === "PER_ORDER_LIMIT") {
    return `At most ${d.limit} ${itemName(d.itemId)} per order.`;
  }
  return errorText(data);
}

// ---------- my orders ----------

const STATUS = {
  PENDING_PAYMENT: { label: "Awaiting payment", pill: "warn" },
  CANCELLED: { label: "Cancelled", pill: "" },
};

async function loadOrders() {
  const r = await api("GET", "/orders");
  const orders = r.data.orders;
  document.getElementById("orders").innerHTML = orders.length === 0
    ? `<div class="card empty">No orders yet.</div>`
    : orders.map(orderCard).join("");
}

function orderCard(o) {
  const pending = o.status === "PENDING_PAYMENT";
  const status = STATUS[o.status] || { label: o.status, pill: "" };
  const gift = o.bonus.length === 0 ? ""
    : o.bonus.every(b => b.included) ? "Included"
    : o.bonus.some(b => b.included) ? "Partly included" : "Ran out";
  return `
    <div class="card">
      <div class="order-head">
        <div class="row">
          <strong>${esc(formatTime(o.createdAt))}</strong>
          <span class="pill ${status.pill}">${esc(status.label)}</span>
        </div>
        <div class="row">
          <strong>${esc(o.currency)} ${esc(o.total)}</strong>
          ${pending ? `<button class="danger small" data-cancel="${esc(o.orderId)}">Cancel</button>` : ""}
        </div>
      </div>
      <div class="order-body">
        <div><h4>Items</h4><ul>${o.lines.map(l =>
          `<li>${l.qty} × ${esc(itemName(l.itemId))}</li>`).join("")}</ul></div>
        ${gift ? `<div><h4>Bonus gift</h4>${gift}</div>` : ""}
        ${pending ? `<div><h4>Pay by</h4>${esc(formatTime(o.paymentDueBy))}</div>` : ""}
      </div>
    </div>`;
}

document.getElementById("orders").addEventListener("click", async event => {
  const button = event.target.closest("button[data-cancel]");
  if (!button) return;
  if (!confirm("Cancel this order?")) return;
  button.disabled = true;
  const r = await api("POST", `/orders/${button.dataset.cancel}/cancel`);
  if (r.ok) showAlert(resultBox, "ok", "Your order has been cancelled.");
  else showAlert(resultBox, "err", errorText(r.data));
  await Promise.all([loadMenu(), loadOrders()]);
});

// ---------- start ----------

if (requireRole("customer", "/login")) {
  loadMenu().then(loadOrders);
}
