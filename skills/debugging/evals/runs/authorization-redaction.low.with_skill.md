# Diagnosis — high confidence

The `Authorization` header was not dropped before authentication. The apparent empty/redacted value in the structured request log is intentional Pino request-log redaction, performed when the log record is serialized, not a mutation of the live Express request.

Evidence from the current checkout:

- `apps/server/src/app.module.ts` configures `nestjs-pino` with `redact: ["req.headers.authorization"]`. Its adjacent comment says bearer tokens are present on `/v1` and `/mcp` requests and must be redacted rather than logged in plaintext.
- `docs/DEBUG.md` explicitly records the expected interpretation: `Authorization` is redacted, and an empty-looking token in a log is redaction rather than a bug.
- Authentication reads the live request header. `ApiKeyGuard` obtains `req.headers.authorization`, rejects an absent/malformed value, then validates the extracted bearer key. JWT authentication is configured with `ExtractJwt.fromAuthHeaderAsBearerToken()`, which likewise requires the header to be present.
- The relevant web proxy does not forward the browser's incoming `Authorization` header verbatim because the browser never receives the bearer token. Instead, `apps/web/lib/admin/backend-fetch.ts` reads the server-side access-token cookie and attaches `Authorization: Bearer <token>` to the backend request. The API-key search path separately attaches its server-side key in `apps/web/lib/api/knowledge-search.ts`.

Causal chain: the bearer value reaches the backend request; the route guard consumes it and permits the request, producing 200; Pino then serializes the request for its completion log with the configured redaction path, so the log deliberately hides that same value. The teammate's proxy-drop explanation is incompatible with a normally guarded route returning 200, since both implemented authentication mechanisms depend on this header.

Remaining uncertainty: no live request/log pair was inspected and the exact protected route was not named. This conclusion therefore covers the implemented API-key- and JWT-guarded routes and the checked web proxies. A route that merely appears protected but has no guard, or a log produced by a different process/configuration than this checkout, would need separate runtime evidence.
