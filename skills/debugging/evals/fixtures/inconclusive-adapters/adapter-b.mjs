export function normalize(value) {
  return value.normalize("NFC").trim().toLowerCase();
}
