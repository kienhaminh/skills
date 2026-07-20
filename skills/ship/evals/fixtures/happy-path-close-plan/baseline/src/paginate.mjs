export function paginate(items, pageSize, page = 1) {
  return items.slice(0, pageSize);
}
