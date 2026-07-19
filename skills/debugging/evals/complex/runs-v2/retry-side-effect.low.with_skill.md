# Diagnosis — medium-high confidence (static analysis)

The duplicate email is caused by a retry across a non-atomic external side effect and its durable completion record. `NotificationWorker.handle` sends the email first, then inserts the processed-job row. When the database insert times out after the mail provider has accepted the send, the handler rejects. The queue retries the same job, sends the email again, and a later insert succeeds. That produces two deliveries, one processed-job row, and an eventually completed queue job—the exact incident pattern.

Evidence from the current code:

- The worker calls `mailer.send(...)` before `processed.insert(job.id)`.
- The queue is configured to retry failed work up to three times.
- The incident records a successful send followed by a database timeout, then eventual job completion and exactly one processed-job row.
- There is no read/check of processed state before sending, nor any atomic transaction spanning the mail provider and database.

Causal chain: mail delivery succeeds → persistence of completion times out and makes the attempt appear failed to the queue → retry repeats the send → a subsequent completion-marker insert succeeds → the queue records completion. The single row is therefore consistent with the second attempt being the only one that persisted, not evidence of a single delivery.

I ruled out a duplicate processed-job record or a queue reporting error as the primary cause because the code creates only one completion record per successful handler attempt and the incident reports one row plus eventual completion. A mail-provider duplicate remains theoretically possible, but it does not explain the specifically observed successful-send/DB-timeout sequence as directly as the retry boundary does.

This conclusion is analysis-derived rather than runtime-confirmed. The remaining uncertainty is timing: the incident log establishes that the mail send completed before the database timeout, but static code alone cannot verify the queue's exact retry classification or whether the provider had irreversibly accepted the message at that moment. Given the configured retries and awaited call order, those assumptions are strongly supported.
