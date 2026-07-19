## Diagnosis

The proxy did not drop the `Authorization` header before authentication. Confidence: high.

The successful protected request requires the same Express request's `req.headers.authorization` to contain `Bearer <token>`: `ApiKeyGuard` rejects a missing or malformed header before it can validate a key, and JWT-protected routes extract the bearer token from that header. Therefore a 200 from the stated authenticated route is strong direct evidence that the header reached the API authentication layer.

The apparently empty/redacted value in the structured request log is intentional. The HTTP logger is configured with pino redaction for `req.headers.authorization`, and the project's debugging documentation explicitly states that an empty-looking Authorization value in logs is redaction, not a bug. Redaction affects the serialized log record, not the in-memory request object the guards inspect.

Remaining uncertainty: without the exact route, request ID, raw log line, and proxy configuration, this checkout cannot establish which proxy hop handled the request or rule out a separate header-rewrite issue on a different request path. It can establish that the reported 200 request was not authenticated after a pre-auth header drop.
