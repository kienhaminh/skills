export function reportRows(entries) {
  return entries.map(({ id, amount }) => ({ id, amount }));
}
