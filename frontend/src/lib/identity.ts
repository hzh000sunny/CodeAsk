const SUBJECT_KEY = "codeask.subject_id";
const NICKNAME_KEY = "codeask.nickname";

function createClientId() {
  if (globalThis.crypto?.randomUUID) {
    return `client_${globalThis.crypto.randomUUID().replaceAll("-", "").slice(0, 18)}`;
  }
  return `client_${Math.random().toString(36).slice(2, 14)}`;
}

export function getSubjectId() {
  const existing = localStorage.getItem(SUBJECT_KEY);
  if (existing) {
    return existing;
  }
  const created = createClientId();
  localStorage.setItem(SUBJECT_KEY, created);
  return created;
}

export function getNickname() {
  return localStorage.getItem(NICKNAME_KEY) ?? "";
}

export function setNickname(nickname: string) {
  const trimmed = nickname.trim();
  if (trimmed) {
    localStorage.setItem(NICKNAME_KEY, trimmed);
  } else {
    localStorage.removeItem(NICKNAME_KEY);
  }
}
