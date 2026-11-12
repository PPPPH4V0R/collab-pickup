// Staff site: inventory, release batches, bonus gifts, new items and combos.

let menu = [];                     // items from GET /menu
const resultBox = document.getElementById("result");

function itemName(itemId) {
  const item = menu.find(i => i.id === itemId);
  return item ? item.name : itemId;
}

// ---------- inventory ----------

async function loadInventory() {
  const r = await api("GET", "/menu");
  menu = r.data.items;
  document.getElementById("inventory").innerHTML = menu.map(i => `
    <tr>
      <td><strong>${esc(i.name)}</strong><br><span class="mono muted">${esc(i.id)}</span>
        ${i.components ? `<br><span class="muted small">${i.components
          .map(c => `${c.qty} × ${esc(itemName(c.itemId))}`).join(" + ")}</span>` : ""}</td>
      <td>${i.kind === "combo" ? `<span class="pill brand">Combo</span>`
            : i.available === null ? `<span class="pill">Unlimited</span>`
            : `<span class="pill">Limited</span>`}</td>
      <td class="num">$${esc(i.price)}</td>
      <td class="num">${i.perOrderLimit ?? "—"}</td>
      <td class="num">${i.available === null ? "—"
            : i.available === 0 ? `<span class="pill err">Sold out</span>` : i.available}</td>
      <td class="num">${i.kind === "combo" ? i.bonusRemaining : "—"}</td>
    </tr>`).join("");
  fillSelect("batch-item", menu.filter(i => i.kind === "single" && i.available !== null));
  fillSelect("gifts-combo", menu.filter(i => i.kind === "combo"));
  document.querySelectorAll("#components select").forEach(s => fillSelect(s, singles()));
}

function singles() {
  return menu.filter(i => i.kind === "single");
}

// Refill a <select> with items, keeping the current choice if it still exists.
function fillSelect(selectOrId, items) {
  const select = typeof selectOrId === "string" ? document.getElementById(selectOrId) : selectOrId;
  const chosen = select.value;
  select.innerHTML = items.map(i => `<option value="${esc(i.id)}">${esc(i.name)}</option>`).join("");
  if (items.some(i => i.id === chosen)) select.value = chosen;
}

document.getElementById("refresh").addEventListener("click", loadInventory);

// After every staff action: show the result, then refresh the inventory.
async function submit(button, method, path, body, successText) {
  button.disabled = true;
  const r = await api(method, path, { body });
  button.disabled = false;
  if (r.ok) showAlert(resultBox, "ok", successText(r.data));
  else showAlert(resultBox, "err", staffErrorText(r.data));
  await loadInventory();
  resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return r.ok;
}

// INVALID_ITEM says which menu rule was broken in details.reason.
function staffErrorText(data) {
  return data.error?.details?.reason || errorText(data);
}

// ---------- release batches ----------

function setReleaseToNow() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById("batch-release").value = now.toISOString().slice(0, 16);
}

document.getElementById("batch-form").addEventListener("submit", event => {
  event.preventDefault();
  const itemId = document.getElementById("batch-item").value;
  const local = document.getElementById("batch-release").value;      // local time, e.g. 2026-11-13T09:30
  submit(event.submitter, "POST", `/items/${encodeURIComponent(itemId)}/batches`, {
    releaseAt: new Date(local).toISOString(),                         // sent in UTC
    quantity: Number(document.getElementById("batch-quantity").value),
  }, b => `${b.quantity} × ${itemName(b.itemId)} ` +
          (new Date(b.releaseAt) <= new Date() ? "added and on sale now." : `go on sale ${formatTime(b.releaseAt)}.`));
});

// ---------- bonus gifts ----------

document.getElementById("gifts-form").addEventListener("submit", event => {
  event.preventDefault();
  const comboId = document.getElementById("gifts-combo").value;
  submit(event.submitter, "POST", `/items/${encodeURIComponent(comboId)}/bonus-gifts`, {
    quantity: Number(document.getElementById("gifts-quantity").value),
  }, c => `${c.name} now has ${c.bonusRemaining} bonus gifts.`);
});

// ---------- new item and new combo ----------

// Suggest an item ID from the name ("Pink Lemonade" -> "pink-lemonade")
// until the ID box is edited by hand.
function suggestCodeFromName(nameId, codeId) {
  const codeBox = document.getElementById(codeId);
  codeBox.addEventListener("input", () => codeBox.dataset.edited = "yes");
  document.getElementById(nameId).addEventListener("input", event => {
    if (codeBox.dataset.edited) return;
    codeBox.value = event.target.value.toLowerCase().trim()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
  });
}

suggestCodeFromName("item-name", "item-id");
suggestCodeFromName("combo-name", "combo-id");

document.getElementById("item-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.getElementById("item-id").value.trim();
  const limit = document.getElementById("item-limit").value;
  const ok = await submit(event.submitter, "POST", "/items", {
    id,
    name: document.getElementById("item-name").value.trim(),
    kind: "single",
    price: document.getElementById("item-price").value.trim(),
    limited: document.getElementById("item-limited").checked,
    perOrderLimit: limit ? Number(limit) : null,
  }, i => `${i.name} added.` + (i.available === 0 ? " Add a release batch to put it on sale." : ""));
  if (ok) {
    event.target.reset();
    delete document.getElementById("item-id").dataset.edited;
    document.getElementById("batch-item").value = id;     // ready for its first batch
  }
});

function addComponentRow() {
  const row = document.createElement("div");
  row.className = "component-row";
  row.innerHTML = `
    <select aria-label="Item"></select>
    <input type="number" min="1" max="20" value="1" aria-label="Quantity">
    <button type="button" class="secondary small" aria-label="Remove">✕</button>`;
  fillSelect(row.querySelector("select"), singles());
  row.querySelector("button").addEventListener("click", () => row.remove());
  document.getElementById("components").appendChild(row);
}

document.getElementById("add-component").addEventListener("click", addComponentRow);

document.getElementById("combo-form").addEventListener("submit", async event => {
  event.preventDefault();
  const components = [...document.querySelectorAll(".component-row")].map(row => ({
    itemId: row.querySelector("select").value,
    qty: Number(row.querySelector("input").value),
  }));
  const ok = await submit(event.submitter, "POST", "/items", {
    id: document.getElementById("combo-id").value.trim(),
    name: document.getElementById("combo-name").value.trim(),
    kind: "combo",
    price: document.getElementById("combo-price").value.trim(),
    components,
    bonusGifts: Number(document.getElementById("combo-gifts").value || 0),
  }, c => `${c.name} added with ${c.bonusRemaining} bonus gifts.`);
  if (ok) {
    event.target.reset();
    delete document.getElementById("combo-id").dataset.edited;
    document.getElementById("components").innerHTML = "";
    addComponentRow();
  }
});

// ---------- start ----------

if (requireRole("staff", "/staff/login")) {
  setReleaseToNow();
  loadInventory().then(addComponentRow);
}
