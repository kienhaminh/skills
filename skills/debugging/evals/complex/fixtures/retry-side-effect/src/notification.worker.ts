export interface Mailer {
  send(recipient: string, body: string): Promise<void>;
}

export interface ProcessedJobs {
  insert(jobId: string): Promise<void>;
}

export type NotificationJob = { id: string; recipient: string; body: string };

export class NotificationWorker {
  constructor(private readonly mailer: Mailer, private readonly processed: ProcessedJobs) {}

  async handle(job: NotificationJob): Promise<void> {
    await this.mailer.send(job.recipient, job.body);
    await this.processed.insert(job.id);
  }
}
