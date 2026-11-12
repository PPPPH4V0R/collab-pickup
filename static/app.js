// Shared by the three test pages. They call the API like any other client.
// The token is kept in sessionStorage: every browser tab has its own, so one
// tab can be logged in as a customer and another as staff.

function token() {
  return sessionStorage.getItem("token");
}

function claims() {
  // The JWT payload is base64url-encoded JSON; the page only reads it to
  // know the role. The server verifies the signature on every request.
  const t = token();
  if (!t) return null;
  return JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
}

function goToLogin() {
  sessionStorage.clear();
  location.href = "/login?next=" + encodeURIComponent(location.pathname);
}

// Called when a page opens: no token, an expired one, or the wrong role
// sends you to the login page.
function requireRole(role) {
  const c = claims();
  if (!c || c.role !== role || c.exp * 1000 < Date.now()) {
    goToLogin();
    return false;
  }
  document.getElementById("who").textContent =
    `Logged in as ${sessionStorage.getItem("username")} (${c.role})`;
  return true;
}

function logout() {
  sessionStorage.clear();
  location.href = "/login";
}

// Send a request; show its status code and JSON body in <pre id="out">
// unless show is false. A 401 while logged in means the token is no longer
// accepted, so go back to the login page.
async function api(method, path, body, headers, show = true) {
  const allHeaders = { "Content-Type": "application/json", ...(headers || {}) };
  if (token()) allHeaders["Authorization"] = "Bearer " + token();
  const res = await fetch(path, { method, headers: allHeaders,
                                  body: body ? JSON.stringify(body) : undefined });
  const data = await res.json();
  if (res.status === 401 && token()) {
    goToLogin();
  }
  if (show) {
    const replayed = res.headers.get("Idempotency-Replayed") ? "  (Idempotency-Replayed: true)" : "";
    document.getElementById("out").textContent =
      `${method} ${path} -> ${res.status}${replayed}\n` + JSON.stringify(data, null, 2);
  }
  return { ok: res.ok, data };
}
