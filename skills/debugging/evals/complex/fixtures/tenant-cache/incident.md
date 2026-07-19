# Incident

A user occasionally sees another tenant's display name. Database traces show every query includes both tenantId and userId. Reports occur only when two tenants have the same userId and requests hit the same long-lived application process.
