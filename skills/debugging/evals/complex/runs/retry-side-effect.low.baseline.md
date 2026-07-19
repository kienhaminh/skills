# Diagnosis: duplicate notification email

## Facts established by static evidence

- `NotificationWorker.handle` sends the email before it records the job as processed:
  `mailer.send(...)` is awaited, then `processed.insert(job.id)` is awaited.
- The queue is configured to retry a failed job up to three times, 30 seconds apart.
- The incident records a successful mail-send log followed by a database timeout, later queue completion, and one processed-job row.
- There is no visible read/check for an already-processed job before the email side effect. The available interfaces also do not show the database insert's conflict or uniqueness behavior.

## Most likely causal mechanism

The first attempt can successfully cause the irreversible external side effect (mail delivery) and then fail at the separate persistence step. If the database timeout rejects the handler, the queue is entitled to retry the same job. A retry executes `mailer.send` again before it has any demonstrated way to detect that the first attempt already sent the message. When a later attempt persists the processed-job row successfully, the queue reports completion. That sequence directly explains two emails with exactly one row: the row records a successful processing attempt, not a durable claim made before sending or a durable record of every successful send.

This conclusion has high confidence about the ordering vulnerability and medium-to-high confidence that the observed duplicate followed that retry path. The exact queue retry decision after the timeout is inferred from the configured retry policy and incident narrative, rather than verified from queue attempt logs.

## Alternatives and limits

- A database timeout is ambiguous: the insert may have committed while its acknowledgement was lost. If so, the retry could still send a duplicate because no pre-send processed-job check is shown; whether it then completes depends on the insert's duplicate-key/upsert semantics, which are not available.
- The duplicated message could instead come from duplicate queue delivery, a second producer enqueue, or mail-provider-level duplicate delivery. The supplied code and incident do not establish any of those paths, and the send-then-timeout ordering makes the retry explanation more directly supported.
- The single processed-job row alone does not prove which attempt inserted it, nor does it prove the first insert did not commit.

## Evidence still needed

- Queue attempt history for this job: attempt count, failure classification, retry scheduling, and final completion attempt.
- Correlated timestamps/request IDs from mail provider acceptance logs, worker logs, and database logs.
- The `ProcessedJobs.insert` implementation and schema: uniqueness constraint, transaction scope, and behavior after a duplicate or timeout.
- Database-side evidence of whether the timed-out insert committed, rolled back, or was cancelled.
- Producer/enqueue audit for the job ID and mail-provider evidence that distinguishes two API send requests from downstream redelivery.
