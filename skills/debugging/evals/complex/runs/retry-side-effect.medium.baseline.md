# Diagnosis: duplicate notification email

## Facts established from the fixture

- `NotificationWorker.handle()` sends the email before it persists any job-processing state: `await mailer.send(...)` precedes `await processed.insert(job.id)` (`src/notification.worker.ts`).
- The queue is configured with up to three retries, 30 seconds apart (`src/queue.config.ts`).
- The incident states that the first attempt logged a successful mail send, then encountered a database timeout; the job was later marked complete and there is exactly one processed-job row.
- The fixture documentation specifically identifies a rare timeout after an external call and directs static analysis of retry and persistence boundaries. No worker or email was run for this diagnosis.

## Most likely causal mechanism

The email send is an external side effect that occurs before the worker has durably recorded successful processing. If the subsequent `processed.insert(job.id)` rejects because of the reported database timeout, `handle()` rejects. Assuming the queue retries rejected jobs, the retry invokes `handle()` again and sends the same email again before it reaches a successful `processed.insert`. The later successful attempt explains both the completed queue job and the single processed-job row.

This is an at-least-once execution boundary with a non-idempotent side effect: a retry cannot distinguish “email was never sent” from “email was sent but persistence failed.” There is no visible read/check of processed state before sending, nor any idempotency key passed to the mailer. A processed-job row written only after the send cannot prevent a duplicate caused by a failure in that gap.

## Alternatives and limits

- The database timeout's outcome is not shown. The first insert may have failed before commit, or it may have committed but timed out while reporting its result. Either outcome leaves the worker without confirmed completion; without a pre-send processed-state check, a retry can still send again. The single final row does not distinguish these cases.
- The displayed worker does not itself show queue retry semantics. The connection between a rejected handler and a retry is strongly suggested by the retry configuration and incident wording, but needs confirmation in the queue integration.
- A duplicate job delivery upstream, a mail-provider resend, or concurrent workers could also produce two emails. The provided evidence favors the post-send database-timeout window because the incident places those events in that order, but it does not rule the alternatives out.
- It is unknown whether `processed.insert(job.id)` is unique, transactional, or coupled to an outbox mechanism; neither the interface nor the fixture contains that implementation.

## Confidence

High confidence that the code exposes the reported duplicate-email failure mode: the send-before-persist ordering creates an unprotected retry window. Medium confidence that this was the exact production sequence, pending confirmation that the database timeout caused the first handler attempt to be retried and that no other delivery path produced the duplicate.

## Evidence still needed

- Queue/worker logs for the job ID: attempt numbers, handler failure, retry scheduling, and final completion.
- Database logs or tracing for the first `processed.insert(job.id)`, including whether its transaction committed despite the timeout.
- Mail-provider delivery/event records and any provider idempotency identifiers, to correlate the two sends.
- The processed-job schema/constraints and queue integration code, including whether workers can process the same job concurrently and how a handler rejection is acknowledged.
