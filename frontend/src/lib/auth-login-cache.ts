const LAST_LOGIN_USERNAME_KEY = "codeask:last-login-username";

export function readLastLoginUsername() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(LAST_LOGIN_USERNAME_KEY) ?? "";
}

export function rememberLastLoginUsername(username: string) {
  if (typeof window === "undefined") {
    return;
  }
  const cleaned = username.trim();
  if (cleaned) {
    window.localStorage.setItem(LAST_LOGIN_USERNAME_KEY, cleaned);
  }
}
