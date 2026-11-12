// Staff page: inventory overview and adding a release batch.

const resultBox = document.getElementById("result");

async function loadInventory() {
  const r = await api("GET", "/menu", { record: false });
  const items = r.data.items;
  document.getElementById("inventory").innerHTML = items.map(i => `
    <tr>
      <td><strong>${esc(i.name)}</strong><br><span class="mono muted">${esc(i.id)}</span></td>
      <td>${i.kind === "combo" ? `<span class="pill brand">Combo</span>`
            : i.available === null ? `<span class="pill">Unlimited</span>`
            : `<span class="pill">Limited</span>`}</td>
      <td class="num">$${esc(i.price)}</td>
      <td class="num">${i.available === null ? "—"
            : i.available === 0 ? `<span class="pill err">Sold out</span>` : i.available}</td>
      <td class="num">${i.kind === "combo" ? i.bonusRemaining : "—"}</td>
    </tr>`).join("");

  // Batches exist only for limited single items.
  const select = document.getElementById("item");
  const chosen = select.value;
  select.innerHTML = items
    .filter(i => i.kind === "single" && i.available !== null)
    .map(i => `<option value="${esc(i.id)}">${esc(i.name)}</option>`).join("");
  if (chosen) select.value = chosen;
}

// The date-time picker starts at "now" in local time.
function setReleaseToNow() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById("release-at").value = now.toISOString().slice(0, 16);
}

document.getElementById("refresh").addEventListener("click", loadInventory);

document.getElementById("batch-form").addEventListener("submit", async event => {
  event.preventDefault();
  const itemId = document.getElementById("item").value;
  const local = document.getElementById("release-at").value;      // e.g. 2026-11-13T09:30
  const quantity = Number(document.getElementById("quantity").value);
  const button = document.getElementById("add");
  button.disabled = true;
  const r = await api("POST", `/items/${encodeURIComponent(itemId)}/batches`, {
    body: { releaseAt: new Date(local).toISOString(), quantity },   // sent in UTC, with "Z"
  });
  button.disabled = false;
  if (r.ok) {
    const b = r.data;
    const released = new Date(b.releaseAt) <= new Date();
    showAlert(resultBox, "ok",
      `<strong>Batch added</strong>${esc(b.batchId)} · ${b.quantity} × ${esc(b.itemId)} · ` +
      (released ? "on sale now" : `goes on sale ${esc(formatTime(b.releaseAt))}`));
  } else {
    showAlert(resultBox, "err", errorHtml(r.data));
  }
  await loadInventory();
});

if (requireRole("staff")) {
  setReleaseToNow();
  loadInventory();
}
