# Debugging

The leak is rare and requires two tenants with overlapping user IDs on one long-lived process. Do not seed data or start services. Trace tenant scope through repository and cache boundaries; distinguish code proof from runtime assumptions.
