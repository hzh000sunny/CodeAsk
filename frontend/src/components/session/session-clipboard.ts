export function formatSessionIdPreview(sessionId: string) {
  if (sessionId.startsWith("sess_")) {
    return `sess_${sessionId.slice(5, 9)}`;
  }
  return sessionId.length <= 9 ? sessionId : sessionId.slice(0, 9);
}

export async function copyTextToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall through to the textarea fallback for browser contexts that expose
      // clipboard but reject access without a permission prompt.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("copy failed");
  }
}
