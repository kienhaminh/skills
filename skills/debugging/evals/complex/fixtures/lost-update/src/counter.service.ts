export interface CounterRepository {
  read(id: string): Promise<{ value: number }>;
  write(id: string, value: number): Promise<void>;
}

export interface AuditSink {
  observeIncrement(id: string): Promise<void>;
}

export class CounterService {
  constructor(private readonly repo: CounterRepository, private readonly audit: AuditSink) {}

  async increment(id: string): Promise<number> {
    const current = await this.repo.read(id);
    await this.audit.observeIncrement(id);
    const next = current.value + 1;
    await this.repo.write(id, next);
    return next;
  }
}
