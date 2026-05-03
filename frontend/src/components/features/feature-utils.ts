export function mergeById<T extends { id: string | number }>(left: T[], right: T[]) {
  const rows = new Map<string | number, T>();
  for (const item of left) {
    rows.set(item.id, item);
  }
  for (const item of right) {
    rows.set(item.id, item);
  }
  return [...rows.values()];
}

export function messageFromError(error: unknown) {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof detail === "object" && detail !== null && "detail" in detail) {
      const nested = (detail as { detail?: unknown }).detail;
      if (typeof nested === "string") {
        return nested;
      }
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败";
}
