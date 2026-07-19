# Debugging

The failure depends on a rare timeout after an external call. Do not send email or run the worker. Analyze the retry and persistence boundaries statically; mark unverified timing assumptions explicitly.
