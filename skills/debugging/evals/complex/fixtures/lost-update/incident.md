# Incident

Two successful requests occasionally increment a counter by one instead of two. It occurs only under concurrency. Both audit events exist, no repository error is logged, and a later read shows the lower value.
