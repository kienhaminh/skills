# Diagnosis — likely duplicate delivery caused by retry across a non-atomic send/persistence boundary (medium confidence)

## Facts observed

- The incident records a successful mail-send log followed by a database timeout on the first attempt; the recipient sometimes receives two copies, the queue later marks the job completed, and one processed-job row exists.
- `NotificationWorker.handle` awaits `mailer.send(...)` before it awaits `processed.insert(job.id)`.
- The worker exposes no processed-job lookup or conditional skip before sending. The only persistence operation shown is `insert`.
- The notification queue permits up to three retries, separated by 30 seconds.
- The project debugging guidance explicitly identifies a rare timeout after an external call and requires static analysis of retry and persistence boundaries. The tech-debt note lists no pre-existing notification-retry debt.

## Causal mechanism

Most likely, the mail provider accepted and delivered the first `mailer.send` call, then `processed.insert` timed out before its successful durable outcome was available to the worker. Because the handler rejects at that point, the queue may retry the same job. On that later attempt, the worker again calls `mailer.send` before recording/consulting processed state, so the recipient receives a second email. If the later insert succeeds, the queue can mark that retry completed and the database will contain exactly one processed-job row.

The broken assumption is that a successful post-send persistence step can safely serve as the sole record preventing repeated external side effects. The send and the database write are separate awaited operations with no atomic transaction spanning the mail provider and database, and the shown code has no pre-send deduplication decision.

## Alternatives and why they fit less well

- **Mailer itself sent two copies for one call:** possible, but it does not explain the specific database timeout followed by queue completion as directly as a retried handler invocation.
- **The first database insert committed despite the client timeout:** possible. In that case, the single row could be from the first attempt, but the shown `insert` contract does not reveal whether a retry would fail, upsert, or otherwise be treated as successful. This explanation needs additional behavior not present in the fixture to explain both a second send and eventual completed job.
- **Two independently enqueued jobs:** possible, but no enqueue path or evidence of two job IDs is provided. The incident's retry timing and configured retries require fewer assumptions.

## Confidence and evidence still needed

This is a static, medium-confidence diagnosis; no code was run and the precise database outcome of the timeout is unverified. Confirmation requires correlated attempt/job IDs and timestamps showing two invocations of `handle` for the same job, provider message IDs showing two accepted send requests, and database/queue traces establishing whether the first `processed.insert` rolled back, committed after the timeout, or was retried idempotently. The `ProcessedJobs.insert` implementation and its uniqueness/conflict semantics are also needed to determine why exactly one row exists and whether that row came from the first or retried attempt.
