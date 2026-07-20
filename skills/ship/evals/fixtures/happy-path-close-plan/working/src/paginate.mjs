export function paginate(items, pageSize, page = 1) {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
