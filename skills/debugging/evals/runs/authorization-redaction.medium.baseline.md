# Diagnosis: authorization redaction is not header loss

The header was not dropped before authentication. Confidence: high.

The server's structured HTTP logger is configured to redact `req.headers.authorization` specifically so bearer credentials never appear in logs. The repository's debugging guide explicitly says that an empty-looking `Authorization` value is redaction, not a bug.

The observed 200 is independent confirmation for a genuinely protected backend route: API-key routes reject a missing or malformed `Authorization: Bearer ...` header before handler execution, and JWT-protected admin routes extract their JWT from that same bearer header. Therefore a request that reached one of those guards and returned 200 had usable authentication material at the guard; a proxy could not have removed that header on that backend hop.

The Next admin proxy also deliberately constructs a fresh backend `Authorization: Bearer <access-token>` header from its httpOnly cookie. It does not need to preserve a browser-supplied Authorization header for the backend call. Its backend request will consequently log the credential as redacted while authenticating successfully.

Remaining uncertainty: without the exact URL and request/response correlation, I cannot identify whether the 200 was for a direct API-key route, a JWT admin route through the Next proxy, or an unguarded route. This conclusion applies when the reported route is actually protected by the current checkout's `ApiKeyGuard` or `JwtAuthGuard`; a 200 from a different/unprotected endpoint would not prove header delivery.
