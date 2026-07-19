export type Profile = { tenantId: string; userId: string; displayName: string };

export interface ProfileRepository {
  find(tenantId: string, userId: string): Promise<Profile>;
}

export interface Cache {
  get(key: string): Promise<Profile | undefined>;
  set(key: string, value: Profile): Promise<void>;
}

export class ProfileService {
  constructor(private readonly repo: ProfileRepository, private readonly cache: Cache) {}

  async getProfile(tenantId: string, userId: string): Promise<Profile> {
    const key = `profile:${userId}`;
    const cached = await this.cache.get(key);
    if (cached) return cached;
    const profile = await this.repo.find(tenantId, userId);
    await this.cache.set(key, profile);
    return profile;
  }
}
