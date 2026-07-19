## Diagnosis — high confidence

The `Authorization` header was not dropped before authentication. The empty/redacted-looking value in the structured request log is intentional log redaction, not the request value that Nest guards receive.

`apps/server/src/app.module.ts` configures `nestjs-pino` with `redact: ["req.headers.authorization"]`. Its adjacent comment says bearer tokens are sent on `/v1` and `/mcp` calls and must be redacted because pino-http would otherwise log the plaintext value. `docs/DEBUG.md` independently names this exact behavior: `Authorization` is redacted, and an empty-looking token in logs is not a bug.

The successful 200 also conflicts with the proxy-drop hypothesis for a protected route. Agent-facing controllers use `ApiKeyGuard`, which reads `req.headers.authorization`, rejects a missing/malformed bearer header with 401, and validates the extracted key before allowing the handler. Admin routes use `JwtAuthGuard`; its Passport strategy extracts the bearer token from the same header. Thus a successful response from a route actually guarded by either mechanism is strong evidence that the backend received a usable header.

For the Next admin proxy specifically, the current route handler delegates to `adminBackendFetch`, and that helper explicitly sends `Authorization: Bearer ${token}` to the backend. No server-side code path was found that deletes or overwrites the header.

### Causal chain

Bearer-authenticated request reaches the backend → pino serializes the request for its structured log and redacts `req.headers.authorization` → authentication guard separately reads the live request header and succeeds → handler returns 200. The log representation therefore cannot be used to infer that the proxy stripped the header.

### Remaining uncertainty

This is a source-based diagnosis; no live request/log pair was captured in this investigation. It assumes the reported 200 came from a route protected by the checkout's `ApiKeyGuard` or `JwtAuthGuard`, rather than an unguarded endpoint. That route identity and the exact deployment/runtime configuration were not supplied, so they remain the only material uncertainty.
