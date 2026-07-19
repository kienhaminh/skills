# Diagnosis: email delivery is retried after an unrecorded successful send

**Confidence: high for the causal mechanism; medium for the timeout timing, which was not reproduced.**

The duplicate is caused by a non-atomic sequence in `NotificationWorker.handle`: it sends the email first, then writes the processed-job record. A database timeout after `mailer.send(...)` causes `processed.insert(job.id)` to reject, so the queue treats the attempt as failed and retries it. Because the prior successful delivery was never durably recorded, the retry sends the same email again; its database insert can then succeed and the queue reports completion.

The incident evidence matches that chain exactly: the first attempt logged a successful mail send followed by a database timeout, the eventual job state was completed, and there is only one processed-job row. One row is therefore consistent with the *successful retry*, not evidence that only one send occurred. The configured retry limit makes this retry path available.

I found no known notification-retry debt documented for this fixture. A queue-level duplicate delivery is a weaker explanation: it does not by itself explain the observed database timeout immediately after the first successful send, whereas the worker's ordering explains every reported fact. The remaining unverified detail is the exact queue behavior on an exception from the handler; the incident's later completion and the configured retries strongly support the inference that it retried the job.
