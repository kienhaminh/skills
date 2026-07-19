# Diagnosis: duplicate notification email

The duplicate is caused by a non-atomic retry boundary around an irreversible side effect. `NotificationWorker.handle` sends the email first and only then inserts the job ID into `ProcessedJobs`. If the database insert times out after the mail provider has accepted the send, the handler rejects even though the recipient has already received the message. The queue is configured to retry failed jobs (up to three times), so a retry runs the same send again before—or regardless of—any durable evidence that the first send happened.

This matches the incident sequence: a successful mail-send log, followed by a database timeout, then eventual queue completion. The single processed-job row is consistent with the later successful attempt persisting the job ID; it does not establish that email was sent only once.

Confidence: high. The ordering and retry policy are explicit in the current code and directly explain the observed duplicate. The exact point at which the database timeout is surfaced relative to server-side commit acknowledgement is unverified, but that timing is not needed for the failure mode: any rejected persistence attempt after a successful external send leaves the retry system unable to distinguish “email already sent” from “email not sent.”
