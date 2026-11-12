// Shared by the pages: talking to the API and remembering who is logged in.
// The pages are ordinary clients of the published contract.
//
// The token is kept in sessionStorage, so every browser tab has its own
// login: one tab can be the customer site and another the staff site.

// ---------- who is logged in ----------

function token() {
  return sessionStorage.getItem("token");
}

// The JWT payload is base64url-encoded JSON. The pages only read the role
// from it to decide where to go; the server checks the signature and the
// role on every request (401 / 403), which is the real protection.
function decodeClaims(jwt) {
  return JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
}

function saveLogin(tokenResponse, username) {
  sessionStorage.setItem("token", tokenResponse.accessToken);
  sessionStorage.setItem("username", username);
}

// Called when a protected page opens. No token, an expired one, or the
// wrong role -> that site's sign-in page. Otherwise fill in the top bar.
function requireRole(role, loginPage) {
  const t = token();
  const claims = t ? decodeClaims(t) : null;
  if (!claims || claims.role !== role || claims.exp * 1000 < Date.now()) {
    sessionStorage.clear();
    location.href = loginPage;
    return false;
  }
  document.getElementById("who-name").textContent = sessionStorage.getItem("username");
  document.getElementById("logout").addEventListener("click", () => {
    sessionStorage.clear();
    location.href = loginPage;
  });
  window.loginPage = loginPage;
  return true;
}

// ---------- calling the API ----------

function newIdempotencyKey() {
  return crypto.randomUUID();
}

// Send a request and return { ok, status, data }. A 401 while logged in
// means the token is no longer accepted: back to the sign-in page.
async function api(method, path, { body, headers } = {}) {
  const allHeaders = { "Content-Type": "application/json", ...(headers || {}) };
  if (token()) allHeaders["Authorization"] = "Bearer " + token();
  const res = await fetch(path, {
    method,
    headers: allHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (res.status === 401 && token() && window.loginPage) {
    sessionStorage.clear();
    location.href = window.loginPage;
  }
  return { ok: res.ok, status: res.status, data };
}

// ---------- small helpers for the pages ----------

// Text from the server goes through esc() before it is put into HTML.
function esc(value) {
  return String(value).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// Show a coloured message box: kind is "ok" or "err".
function showAlert(element, kind, text) {
  element.className = "alert " + kind;
  element.textContent = text;
}

function hideAlert(element) {
  element.className = "hidden";
  element.textContent = "";
}

// The sentence to show for an error response { error: { code, message, details } }.
function errorText(data) {
  return (data.error && data.error.message) || "Something went wrong. Please try again.";
}

function formatTime(iso) {
  return new Date(iso).toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" });
}
