// Staff sign-in page. There is no sign-up: staff accounts are created by
// the shop. A customer account is refused here and its token is not kept.

sessionStorage.clear();        // opening the sign-in page logs this tab out

const alertBox = document.getElementById("alert");

document.getElementById("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  if (!username || !password) {
    showAlert(alertBox, "err", "Enter your username and password.");
    return;
  }
  const button = document.getElementById("submit");
  button.disabled = true;
  const r = await api("POST", "/auth/login", { body: { username, password } });
  button.disabled = false;
  if (!r.ok) {
    showAlert(alertBox, "err", errorText(r.data));
  } else if (decodeClaims(r.data.accessToken).role !== "staff") {
    showAlert(alertBox, "err", "This account does not have staff access.");
  } else {
    saveLogin(r.data, username);
    location.href = "/staff";
  }
});
