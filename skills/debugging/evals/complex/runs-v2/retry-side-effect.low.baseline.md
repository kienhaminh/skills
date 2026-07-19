# Diagnosis: duplicate notification email

The duplicate is caused by retrying a job whose external side effect has already succeeded. `NotificationWorker.handle` sends the email before writing the processed-job record. When `mailer.send(...)` succeeds but `processed.insert(job.id)` times out, the handler rejects, so the queue is entitled to retry it (up to three times). The retry invokes `mailer.send(...)` again and can then complete the database insert; this exactly matches the incident sequence: one successful send followed by a database timeout, eventual queue completion, and one processed-job row.

The processed-job table does not prevent this particular duplicate because it is updated only after the email is sent, and this handler never checks it before sending. A single row is therefore expected after a successful retry, not evidence that the email was sent once.

Confidence: high. The execution ordering in the current worker and the configured retry behavior directly explain every reported observation. This conclusion assumes the reported timeout causes the queue handler to fail, which is the normal consequence of the awaited rejected `processed.insert` promise shown here.
