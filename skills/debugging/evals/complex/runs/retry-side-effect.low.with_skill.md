# Diagnosis: retry replays a non-idempotent email send (high confidence, static analysis)

The most likely cause is that a database timeout after the first successful `mailer.send()` makes the job attempt fail, so the queue retries the whole handler and sends the same email again. The later successful attempt records the job as processed, which explains both the eventual completed status and the single processed-job row. This conclusion is derived from static code and the incident report; the exact retry timeline has not been verified at runtime.

## Facts checked

- The incident reports a successful first mail-send log followed by a database timeout, then eventual queue completion and exactly one processed-job row.
- `NotificationWorker.handle()` awaits `mailer.send()` before it calls `processed.insert(job.id)`.
- There is no read/check for a prior processed job and no idempotency key passed to the mailer in the inspected code.
- Queue configuration permits up to three retries, with a 30-second delay.
- The fixture documentation explicitly identifies a rare timeout after an external call and directs static analysis of retry and persistence boundaries.
- The tech-debt document lists no known notification retry debt.

## Causal mechanism

1. An attempt invokes the external mail provider successfully, so the recipient receives the message.
2. The following persistence operation times out. If that timeout rejects `handle()`, the worker has no local recovery path and the attempt is reported as failed.
3. The queue is configured to retry failed jobs. A retry begins at the start of `handle()`, not after the already-completed mail call.
4. Because sending precedes the processed-job write and the code has no pre-send deduplication or mail-provider idempotency boundary, the retry sends the email a second time.
5. The retry's processed-job insert succeeds, yielding exactly one row, and the queue can then mark the job completed.

The broken assumption is that the external side effect and the database acknowledgement behave like one atomic operation. They do not: a failure between them creates an ambiguous outcome in which the email is already delivered but the queue lacks durable evidence that it was handled.

## Alternatives considered

- **Mailer/provider independently delivered one request twice:** possible, but it does not explain why the duplicate correlates with a database timeout immediately after a successful send as directly as a whole-job retry does.
- **The database insert committed despite the timeout:** possible at the database/client boundary, but the worker does not inspect stored state before retrying, so this would still permit a second send. The incident's single row cannot distinguish this from a first insert that never committed and a later retry insert that did.
- **Concurrent duplicate queue deliveries:** not established by the available material. It could also duplicate sends, but no concurrency, lease, or duplicate-enqueue evidence was supplied; the reported send-then-timeout sequence plus configured retries requires fewer assumptions.

## Confidence and evidence still needed

Confidence is **high for the causal design flaw** (a retry can replay a sent email after persistence fails) and **medium-high that it caused this incident**, because no runtime logs or queue implementation were inspected.

To confirm the incident mechanism, collect: the job ID's per-attempt queue logs and attempt count; timestamps/message-provider IDs for both deliveries; the error and transaction outcome of the first `processed.insert`; and the queue framework's documented behavior when `handle()` rejects or a worker loses acknowledgement after completion. Those records would distinguish a normal retry from duplicate delivery, a provider-side duplicate, or an insert that committed before the timeout was observed.
