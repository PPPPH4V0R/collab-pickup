// Login page: log in or sign up, then go to the page for your role.

sessionStorage.clear();        // opening the login page logs this tab out

const alertBox = document.getElementById("alert");
const USERNAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;   // same rule as the contract

// "/login?next=/staff" tells the user why they are here.
const next = new URLSearchParams(location.search).get("next");
if (next) {
  showAlert(document.getElementById("note"), "info", `Log in to open <strong>${esc(next)}</strong>`);
}

// ---------- the two tabs ----------

function showTab(name) {
  const login = name === "login";
  document.getElementById("tab-login").classList.toggle("active", login);
  document.getElementById("tab-signup").classList.toggle("active", !login);
  document.getElementById("login-form").classList.toggle("hidden", !login);
  document.getElementById("signup-form").classList.toggle("hidden", login);
  hideAlert(alertBox);
}

document.getElementById("tab-login").addEventListener("click", () => showTab("login"));
document.getElementById("tab-signup").addEventListener("click", () => showTab("signup"));

// After login or sign-up, the role in the token decides the page.
function enter(tokenResponse, username) {
  saveLogin(tokenResponse, username);
  location.href = claims().role === "staff" ? "/staff" : "/customer";
}

// ---------- log in ----------

document.getElementById("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  if (!username || !password) {
    showAlert(alertBox, "err", "Enter your username and password.");
    return;
  }
  const button = document.getElementById("login-submit");
  button.disabled = true;
  const r = await api("POST", "/auth/login", { body: { username, password } });
  button.disabled = false;
  if (r.ok) enter(r.data, username);
  else showAlert(alertBox, "err", errorHtml(r.data));
});

// ---------- sign up (with checks before anything is sent) ----------

function signupProblems() {
  const username = document.getElementById("signup-username").value.trim();
  const password = document.getElementById("signup-password").value;
  const confirm = document.getElementById("signup-confirm").value;
  return {
    username: username && !USERNAME_PATTERN.test(username)
      ? "Only letters, digits, _ and -, up to 64 characters." : "",
    password: password && password.length < 8 ? "At least 8 characters." : "",
    confirm: confirm && confirm !== password ? "The passwords do not match." : "",
  };
}

function showSignupHints() {
  const p = signupProblems();
  const hint = (id, text, normal) => {
    const el = document.getElementById(id);
    el.textContent = text || normal;
    el.classList.toggle("bad", Boolean(text));
  };
  hint("signup-username-hint", p.username, "Letters, digits, _ and -, up to 64 characters.");
  hint("signup-password-hint", p.password, "At least 8 characters.");
  hint("signup-confirm-hint", p.confirm, "");
}

["signup-username", "signup-password", "signup-confirm"].forEach(id =>
  document.getElementById(id).addEventListener("input", showSignupHints));

document.getElementById("signup-form").addEventListener("submit", async event => {
  event.preventDefault();
  const username = document.getElementById("signup-username").value.trim();
  const password = document.getElementById("signup-password").value;
  const confirm = document.getElementById("signup-confirm").value;
  showSignupHints();
  const p = signupProblems();
  if (!username || !password || !confirm || p.username || p.password || p.confirm) {
    showAlert(alertBox, "err", "Please fix the fields marked in red.");
    return;
  }
  const button = document.getElementById("signup-submit");
  button.disabled = true;
  const r = await api("POST", "/auth/register", { body: { username, password } });
  button.disabled = false;
  if (r.ok) enter(r.data, username);
  else showAlert(alertBox, "err", errorHtml(r.data));
});
