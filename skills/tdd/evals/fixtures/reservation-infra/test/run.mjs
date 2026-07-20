if (!process.env.RESERVATION_TEST_DATABASE_URL) {
  console.error("required external reservation test harness is unavailable");
  process.exit(78);
}

await import("./reservation.integration.test.mjs");
