// Shared by the three pages: talking to the API and remembering who is
// logged in. The pages are ordinary clients of the published contract.
//
// The token is kept in sessionStorage, so every browser tab has its own
// login: one tab can be a customer and another staff.

// ---------- who is logged in ----------

function token() {
  return sessionStorage.getItem("token");
}

function claims() {
  // The JWT payload is base64url-encoded JSON. The page only reads the role
  // from it to pick a page; the server verifies the signature on every call.
  const t = token();
  if (!t) return null;
  return JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
}

function saveLogin(tokenResponse, username) {
  sessionStorage.setItem("token", tokenResponse.accessToken);
  sessionStorage.setItem("username", username);
}

function logout() {
  sessionStorage.clear();
  location.href = "/login";
}

function goToLogin() {
  sessionStorage.clear();
  location.href = "/login?next=" + encodeURIComponent(location.pathname);
}

// Called when a protected page opens. No token, an expired one, or the
// wrong role -> back to the login page. Otherwise fill in the top bar.
function requireRole(role) {
  const c = claims();
  if (!c || c.role !== role || c.exp * 1000 < Date.now()) {
    goToLogin();
    return false;
  }
  document.getElementById("who-name").textContent = sessionStorage.getItem("username");
  document.getElementById("who-role").textContent = c.role;
  document.getElementById("logout").addEventListener("click", logout);
  return true;
}

// ---------- calling the API ----------

function newIdempotencyKey() {
  return crypto.randomUUID();
}

// Send a request and return { ok, status, data, replayed }.
// record = true also shows it in the "API response" panel (user actions);
// background refreshes pass record = false so they do not hide it.
// A 401 while logged in means the token is no longer accepted.
async function api(method, path, { body, headers, record = true } = {}) {
  const allHeaders = { "Content-Type": "application/json", ...(headers || {}) };
  if (token()) allHeaders["Authorization"] = "Bearer " + token();
  const res = await fetch(path, {
    method,
    headers: allHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  const replayed = res.headers.get("Idempotency-Replayed") === "true";
  if (record) showApiResponse(method, path, res.status, data, replayed);
  if (res.status === 401 && token()) goToLogin();
  return { ok: res.ok, status: res.status, data, replayed };
}

// The collapsible panel at the bottom of each page, for showing the TA the
// real status codes and JSON.
function showApiResponse(method, path, status, data, replayed) {
  const out = document.getElementById("api-out");
  if (!out) return;
  const pill = document.getElementById("api-status");
  pill.textContent = status + (replayed ? " replayed" : "");
  pill.className = "pill " + (status < 300 ? "ok" : status < 500 ? "err" : "warn");
  out.textContent = `${method} ${path}\n${status}${replayed ? "  Idempotency-Replayed: true" : ""}\n\n`
                    + JSON.stringify(data, null, 2);
}

// ---------- small helpers for the pages ----------

// Text from the server goes through esc() before it is put into HTML.
function esc(value) {
  return String(value).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// Show a coloured message box: kind is "ok", "err" or "info".
function showAlert(element, kind, html) {
  element.className = "alert " + kind;
  element.innerHTML = html;
}

function hideAlert(element) {
  element.className = "hidden";
  element.innerHTML = "";
}

// The error shape of the contract: { error: { code, message, details } }.
function errorHtml(data) {
  const e = data.error || { code: "ERROR", message: "Something went wrong." };
  return `<strong>${esc(e.code)}</strong>${esc(e.message)}`;
}

function formatTime(iso) {
  // English like the rest of the page, in the browser's own time zone.
  return new Date(iso).toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" });
}
