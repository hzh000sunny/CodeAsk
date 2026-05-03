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
