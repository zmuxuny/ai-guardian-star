import { CloudService } from './CloudService';
import { STORE_KEY_AI_ENABLED, STORE_KEY_AI_ACCESS_LEVEL, STORE_KEY_AI_POLICY_READY,
  STORE_KEY_AI_POLICY_STAMP } from '../config';

export interface AiPermission {
  enabled: boolean;
  accessLevel: string;
  version: number;
}

interface PermissionResponse {
  success: boolean;
  message?: string;
  settings?: AiPermission;
}

interface PermissionSave extends AiPermission {}
class EmptyPermissionRequest {}

/** Cloud consent is authoritative; no local grant is restored on network failure. */
export class AiPermissionService {
  private static instance: AiPermissionService;
  private owner: string = '';
  private policy: AiPermission = { enabled: false, accessLevel: 'privacy', version: 0 };
  private saving: boolean = false;
  private syncPromise: Promise<boolean> | null = null;

  public static getInstance(): AiPermissionService {
    if (!AiPermissionService.instance) AiPermissionService.instance = new AiPermissionService();
    return AiPermissionService.instance;
  }

  private apply(owner: string, policy: AiPermission): void {
    if (owner === '' || CloudService.getInstance().getSessionUserKey() !== owner) {
      throw new Error('登录账号已变化，请重试');
    }
    if (policy.enabled !== true && policy.enabled !== false) throw new Error('服务器权限格式无效：开关');
    if (policy.accessLevel !== 'basic' && policy.accessLevel !== 'privacy' && policy.accessLevel !== 'full') {
      throw new Error('服务器权限格式无效：数据范围');
    }
    if (typeof policy.version !== 'number' || policy.version < 0 || Math.floor(policy.version) !== policy.version) {
      throw new Error('服务器权限格式无效：版本');
    }
    this.owner = owner;
    this.policy = policy;
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_ENABLED, policy.enabled);
    AppStorage.setOrCreate<string>(STORE_KEY_AI_ACCESS_LEVEL, policy.accessLevel);
    const stamp = `${owner}:${policy.version}:${policy.enabled}:${policy.accessLevel}`;
    if (AppStorage.get<string>(STORE_KEY_AI_POLICY_STAMP) !== stamp) {
      AppStorage.setOrCreate<string>(STORE_KEY_AI_POLICY_STAMP, stamp);
    }
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_POLICY_READY, true);
  }

  public invalidate(): void {
    this.owner = '';
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_POLICY_READY, false);
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_ENABLED, false);
    AppStorage.setOrCreate<string>(STORE_KEY_AI_POLICY_STAMP, 'unverified');
  }

  public current(): AiPermission | null {
    if (this.owner !== CloudService.getInstance().getSessionUserKey()
      || AppStorage.get<boolean>(STORE_KEY_AI_POLICY_READY) !== true || this.saving) return null;
    return { enabled: this.policy.enabled, accessLevel: this.policy.accessLevel, version: this.policy.version };
  }

  public async sync(): Promise<boolean> {
    if (this.saving) return false;
    if (this.syncPromise) return this.syncPromise;
    this.syncPromise = this.readCloud();
    try { return await this.syncPromise; } finally { this.syncPromise = null; }
  }

  private async readCloud(): Promise<boolean> {
    const owner = CloudService.getInstance().getSessionUserKey();
    let status: number = 0;
    try {
      const response = await CloudService.getInstance().authenticatedPost('/api/ai/settings/read', new EmptyPermissionRequest());
      status = response.responseCode;
      const data = JSON.parse(response.result) as PermissionResponse;
      if (response.responseCode !== 200 || !data.success || !data.settings) throw new Error('权限同步失败');
      this.apply(owner, data.settings);
      return true;
    } catch (error) {
      console.warn(`[AiPermission] sync failed status=${status} reason=${(error as Error).message}`);
      this.invalidate();
      return false;
    }
  }

  public async save(enabled: boolean, accessLevel: string): Promise<void> {
    if (this.saving) throw new Error('正在保存，请稍候');
    if (this.syncPromise) await this.syncPromise;
    if (!this.current() && !await this.sync()) throw new Error('无法同步 AI 权限，请联网后重试');
    const policy = this.current();
    if (!policy) throw new Error('权限尚未同步，请重试');
    const owner = this.owner;
    const request: PermissionSave = { enabled, accessLevel, version: policy.version };
    this.saving = true;
    // Stop new chats and ignore pending replies while consent is changing.
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_POLICY_READY, false);
    try {
      const response = await CloudService.getInstance().authenticatedPost('/api/ai/settings/save', request);
      const data = JSON.parse(response.result) as PermissionResponse;
      if (response.responseCode !== 200 || !data.success || !data.settings) {
        throw new Error(data.message || '权限未保存，请重试');
      }
      this.apply(owner, data.settings);
    } catch (error) {
      this.invalidate();
      throw new Error((error as Error).message || '权限保存失败，请重试');
    } finally {
      this.saving = false;
    }
  }
}
