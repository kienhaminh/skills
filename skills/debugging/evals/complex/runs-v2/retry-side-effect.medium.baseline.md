# Diagnosis: retry crosses a non-atomic side effect

The duplicate email is caused by the notification handler performing the irreversible external action before recording durable completion:

```ts
await this.mailer.send(job.recipient, job.body);
await this.processed.insert(job.id);
```

If `mailer.send` succeeds and the subsequent database insert times out, `handle` rejects. The queue is configured to retry failed jobs up to three times, and the retry invokes the same handler from the beginning. There is no read/check of `processed` before `mailer.send`, nor any other idempotency boundary around the mail operation, so that retry sends the email again.

This also explains the incident's otherwise conflicting-looking evidence: the retry can send the second email and then successfully insert the one processed-job row, after which the queue reports the job completed. A single processed row therefore records only eventual successful completion; it cannot establish that the preceding external send occurred exactly once.

Confidence: high. The static control flow and retry configuration directly match the reported sequence. The only unverified detail is whether the timed-out insert reached the database; that does not change the root cause, because the worker never uses the processed-job record to suppress a resend before sending mail.
