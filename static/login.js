// Customer sign-in page: log in or sign up, then go to /customer.
// Staff use their own page, /staff/login.

sessionStorage.clear();        // opening the sign-in page logs this tab out

const alertBox = document.getElementById("alert");
const USERNAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;   // same rule as the contract
const WRONG_LOGIN = "Wrong username or password.";  // the server's INVALID_CREDENTIALS message

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

// Only customer accounts sign in here. A staff account gets the same answer
// as a wrong password (so the page does not reveal that the account exists),
// and its token is not kept.
function enter(tokenResponse, username) {
  if (decodeClaims(tokenResponse.accessToken).role !== "customer") {
    showAlert(alertBox, "err", WRONG_LOGIN);
    return;
  }
  saveLogin(tokenResponse, username);
  location.href = "/customer";
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
  else showAlert(alertBox, "err", errorText(r.data));
});

// ---------- sign up: problems are shown only when there are some ----------

function signupProblems() {
  const username = document.getElementById("signup-username").value.trim();
  const password = document.getElementById("signup-password").value;
  const confirm = document.getElementById("signup-confirm").value;
  return {
    "signup-username-hint": !username ? "Enter a username."
      : !USERNAME_PATTERN.test(username) ? "Use only letters, digits, _ and -." : "",
    "signup-password-hint": password.length < 8 ? "Use at least 8 characters." : "",
    "signup-confirm-hint": confirm !== password ? "The passwords do not match." : "",
  };
}

document.getElementById("signup-form").addEventListener("submit", async event => {
  event.preventDefault();
  hideAlert(alertBox);
  const problems = signupProblems();
  for (const [id, text] of Object.entries(problems)) document.getElementById(id).textContent = text;
  if (Object.values(problems).some(Boolean)) return;

  const username = document.getElementById("signup-username").value.trim();
  const password = document.getElementById("signup-password").value;
  const button = document.getElementById("signup-submit");
  button.disabled = true;
  const r = await api("POST", "/auth/register", { body: { username, password } });
  button.disabled = false;
  if (r.ok) enter(r.data, username);
  else showAlert(alertBox, "err", errorText(r.data));
});
