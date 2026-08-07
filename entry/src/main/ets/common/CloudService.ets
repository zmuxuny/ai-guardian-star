/** 云端账号会话。Access Token 只驻留内存；勾选“记住我”时 Refresh Token 写入 Asset Store。 */
import http from '@ohos.net.http';
import { asset } from '@kit.AssetStoreKit';
import { util } from '@kit.ArkTS';
import { BusinessError } from '@kit.BasicServicesKit';
import { ECS_BASE_URL } from '../config';

export interface CloudUser {
  username: string;
  nickname: string;
  phone: string;
  avatarPath: string;
  avatarVersion?: number;
  email: string;
  address: string;
  createTime: number;
}

export interface CloudResult {
  success: boolean;
  message: string;
  user?: CloudUser;
  accessToken?: string;
  refreshToken?: string;
  challengeId?: string;
  expiresIn?: number;
  imageBase64?: string;
  mimeType?: string;
  updatedAt?: number;
}

export interface CloudHttpResponse {
  responseCode: number;
  result: string;
}

interface LoginRequest {
  username: string;
  passwordHash: string;
}

interface RefreshRequest {
  refreshToken: string;
}

interface SendOtpRequest {
  phone: string;
}

interface RegisterRequest {
  phone: string;
  passwordHash: string;
  verifyCode: string;
  challengeId: string;
  nickname?: string;
}

interface ChangePasswordRequest {
  oldPasswordHash: string;
  newPasswordHash: string;
}

interface VerifyResetCodeRequest {
  phone: string;
  verifyCode: string;
  challengeId: string;
}

interface ResetPasswordRequest {
  phone: string;
  passwordHash: string;
  challengeId: string;
}

interface ContactOtpRequest {
  kind: string;
  value: string;
}

interface ContactUpdateRequest extends ContactOtpRequest {
  verifyCode: string;
  challengeId: string;
}

interface AvatarUploadRequest {
  imageBase64: string;
  mimeType: string;
}

interface DeleteUserRequest {
  passwordHash: string;
}

interface AllowedProfileUpdate {
  nickname?: string;
  address?: string;
}

interface RequestHeaders {
  'Content-Type': string;
  'Authorization'?: string;
}

class EmptyRequest {}

/** 兼容现有调用方；CloudService 只发送后端允许的非敏感字段。 */
export class CloudUpdateFields {
  username: string = '';
  newUsername: string = '';
  nickname: string = '';
  avatarPath: string = '';
  phone: string = '';
  email: string = '';
  address: string = '';
  passwordHash: string = '';
}

export class CloudService {
  private static instance: CloudService;
  private static readonly SESSION_ASSET_ALIAS: Uint8Array =
    new util.TextEncoder().encodeInto('guardian_cloud_session');
  private accessToken: string = '';
  private refreshToken: string = '';
  private sessionUserKey: string = '';
  private rememberSession: boolean = false;
  private refreshPromise: Promise<boolean> | null = null;

  private constructor() {}

  public static getInstance(): CloudService {
    if (!CloudService.instance) {
      CloudService.instance = new CloudService();
    }
    return CloudService.instance;
  }

  public hasSession(): boolean {
    return this.accessToken !== '' && this.refreshToken !== '' && this.sessionUserKey !== '';
  }

  public getSessionUserKey(): string {
    return this.sessionUserKey;
  }

  public clearSession(): void {
    this.accessToken = '';
    this.refreshToken = '';
    this.sessionUserKey = '';
    this.rememberSession = false;
  }

  private async persistSession(): Promise<void> {
    const attributes: asset.AssetMap = new Map();
    attributes.set(asset.Tag.ALIAS, CloudService.SESSION_ASSET_ALIAS);
    attributes.set(asset.Tag.SECRET,
      new util.TextEncoder().encodeInto(JSON.stringify([this.sessionUserKey, this.refreshToken])));
    attributes.set(asset.Tag.ACCESSIBILITY, asset.Accessibility.DEVICE_FIRST_UNLOCKED);
    attributes.set(asset.Tag.CONFLICT_RESOLUTION, asset.ConflictResolution.OVERWRITE);
    try {
      await asset.add(attributes);
    } catch (e) {
      const error = e as BusinessError;
      throw new Error(`保存登录凭据失败: ${error.code} ${error.message}`);
    }
  }

  public async clearPersistedSession(): Promise<void> {
    const query: asset.AssetMap = new Map();
    query.set(asset.Tag.ALIAS, CloudService.SESSION_ASSET_ALIAS);
    try {
      await asset.remove(query);
    } catch (e) {
      const error = e as BusinessError;
      if (error.code !== 24000002) {
        throw new Error('Asset Store 清理失败 code=' + error.code);
      }
    }
  }

  public async restorePersistedSession(): Promise<boolean> {
    this.clearSession();
    const query: asset.AssetMap = new Map();
    query.set(asset.Tag.ALIAS, CloudService.SESSION_ASSET_ALIAS);
    query.set(asset.Tag.RETURN_TYPE, asset.ReturnType.ALL);
    try {
      const records = await asset.query(query);
      if (records.length !== 1) return false;
      const secret = records[0].get(asset.Tag.SECRET) as Uint8Array;
      const saved = JSON.parse(new util.TextDecoder().decodeToString(secret)) as string[];
      if (saved.length !== 2 || saved[0] === '' || saved[1] === '') {
        await this.clearPersistedSession();
        return false;
      }
      this.sessionUserKey = saved[0];
      this.refreshToken = saved[1];
      this.rememberSession = true;
      return await this.performRefresh();
    } catch (e) {
      const error = e as BusinessError;
      if (error.code !== 24000002) {
        console.warn('[CloudService]: 恢复持久会话失败 code=' + error.code);
      }
      this.clearSession();
      return false;
    }
  }

  private async requestRaw(path: string, method: http.RequestMethod, body: Object,
    authenticated: boolean, readTimeout: number, retryAfterRefresh: boolean): Promise<CloudHttpResponse> {
    if (authenticated && this.accessToken === '') {
      return { responseCode: 401, result: '{"success":false,"message":"未登录"}' };
    }

    const requestAccessToken = authenticated ? this.accessToken : '';
    const req = http.createHttp();
    let response: CloudHttpResponse;
    try {
      const headers: RequestHeaders = authenticated
        ? { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + requestAccessToken }
        : { 'Content-Type': 'application/json' };
      const raw = await req.request(ECS_BASE_URL + path, {
        method: method,
        header: headers,
        extraData: JSON.stringify(body),
        connectTimeout: 10000,
        readTimeout: readTimeout,
        expectDataType: http.HttpDataType.STRING,
      });
      response = { responseCode: raw.responseCode, result: raw.result as string };
    } catch (_e) {
      return { responseCode: 0, result: '{"success":false,"message":"网络不可用"}' };
    } finally {
      req.destroy();
    }

    if (authenticated && response.responseCode === 401 && retryAfterRefresh) {
      if (await this.refreshSession(requestAccessToken)) {
        return this.requestRaw(path, method, body, true, readTimeout, false);
      }
    }
    if (authenticated && response.responseCode === 401 && !retryAfterRefresh) {
      await this.clearPersistedSession();
      this.clearSession();
    }
    return response;
  }

  private async refreshSession(failedAccessToken: string): Promise<boolean> {
    if (this.accessToken !== '' && this.accessToken !== failedAccessToken) {
      return true;
    }
    if (this.refreshPromise !== null) {
      return this.refreshPromise;
    }
    this.refreshPromise = this.performRefresh();
    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async performRefresh(): Promise<boolean> {
    if (this.refreshToken === '') {
      await this.clearPersistedSession();
      this.clearSession();
      return false;
    }
    const body: RefreshRequest = { refreshToken: this.refreshToken };
    const response = await this.requestRaw('/api/refresh', http.RequestMethod.POST, body, false, 10000, false);
    try {
      const result = JSON.parse(response.result) as CloudResult;
      if (response.responseCode === 200 && result.success && result.accessToken && result.refreshToken) {
        this.accessToken = result.accessToken;
        this.refreshToken = result.refreshToken;
        if (this.rememberSession) {
          await this.persistSession();
        }
        return true;
      }
    } catch (_e) {}
    if (response.responseCode === 400 || response.responseCode === 401) {
      await this.clearPersistedSession();
    }
    this.clearSession();
    return false;
  }

  private parseResult(response: CloudHttpResponse): CloudResult {
    try {
      return JSON.parse(response.result) as CloudResult;
    } catch (_e) {
      return { success: false, message: response.responseCode === 0 ? '网络不可用' : '服务器响应格式错误' };
    }
  }

  public async authenticatedPost(path: string, body: Object, readTimeout: number = 10000): Promise<CloudHttpResponse> {
    return this.requestRaw(path, http.RequestMethod.POST, body, true, readTimeout, true);
  }

  public async login(username: string, passwordHash: string, rememberMe: boolean = false): Promise<CloudResult> {
    await this.clearPersistedSession();
    this.clearSession();
    const body: LoginRequest = { username: username, passwordHash: passwordHash };
    const result = this.parseResult(
      await this.requestRaw('/api/login', http.RequestMethod.POST, body, false, 10000, false)
    );
    if (result.success && result.accessToken && result.refreshToken) {
      this.accessToken = result.accessToken;
      this.refreshToken = result.refreshToken;
      this.sessionUserKey = username;
      this.rememberSession = rememberMe;
      if (rememberMe) {
        await this.persistSession();
      }
      return result;
    }
    if (result.success) {
      return { success: false, message: '服务器未返回有效会话' };
    }
    return result;
  }

  public async sendRegistrationCode(phone: string): Promise<CloudResult> {
    const body: SendOtpRequest = { phone: phone };
    return this.parseResult(
      await this.requestRaw('/api/otp/send', http.RequestMethod.POST, body, false, 20000, false)
    );
  }

  public async register(phone: string, passwordHash: string, verifyCode: string,
    challengeId: string, rememberMe: boolean = false): Promise<CloudResult> {
    await this.clearPersistedSession();
    this.clearSession();
    const body: RegisterRequest = {
      phone: phone,
      passwordHash: passwordHash,
      verifyCode: verifyCode,
      challengeId: challengeId,
    };
    const result = this.parseResult(
      await this.requestRaw('/api/register', http.RequestMethod.POST, body, false, 20000, false)
    );
    if (result.success && result.accessToken && result.refreshToken && result.user) {
      this.accessToken = result.accessToken;
      this.refreshToken = result.refreshToken;
      this.sessionUserKey = result.user.username || phone;
      this.rememberSession = rememberMe;
      if (rememberMe) {
        await this.persistSession();
      }
      return result;
    }
    if (result.success) {
      return { success: false, message: '服务器未返回有效会话' };
    }
    return result;
  }

  /** 忘记密码：向已注册手机号发送短信验证码 */
  public async sendPasswordResetCode(phone: string): Promise<CloudResult> {
    const body: SendOtpRequest = { phone: phone };
    return this.parseResult(
      await this.requestRaw('/api/password/otp/send', http.RequestMethod.POST, body, false, 20000, false)
    );
  }

  /** 忘记密码：校验短信验证码。通过后该会话才允许设置新密码。 */
  public async verifyPasswordResetCode(phone: string, verifyCode: string,
    challengeId: string): Promise<CloudResult> {
    const body: VerifyResetCodeRequest = {
      phone: phone,
      verifyCode: verifyCode,
      challengeId: challengeId,
    };
    return this.parseResult(
      await this.requestRaw('/api/password/otp/verify', http.RequestMethod.POST, body, false, 20000, false)
    );
  }

  /** 忘记密码：凭已验证的会话设置新密码。成功后服务端会清掉该账号全部会话。 */
  public async resetPassword(phone: string, passwordHash: string,
    challengeId: string): Promise<CloudResult> {
    const body: ResetPasswordRequest = {
      phone: phone,
      passwordHash: passwordHash,
      challengeId: challengeId,
    };
    return this.parseResult(
      await this.requestRaw('/api/password/reset', http.RequestMethod.POST, body, false, 20000, false)
    );
  }

  public async getMe(): Promise<CloudResult> {
    return this.parseResult(
      await this.requestRaw('/api/me', http.RequestMethod.GET, new EmptyRequest(), true, 10000, true)
    );
  }

  public async logout(): Promise<CloudResult> {
    let result: CloudResult = { success: false, message: '未登录' };
    try {
      if (this.hasSession()) {
        result = this.parseResult(await this.authenticatedPost('/api/logout', new EmptyRequest()));
      }
      return result;
    } finally {
      this.clearSession();
      await this.clearPersistedSession();
    }
  }

  public async updateUser(fields: CloudUpdateFields): Promise<CloudResult> {
    const body: AllowedProfileUpdate = {};
    if (fields.nickname !== '') body.nickname = fields.nickname;
    if (fields.address !== '') body.address = fields.address;
    return this.parseResult(await this.authenticatedPost('/api/updateUser', body));
  }

  public async sendContactCode(kind: string, value: string): Promise<CloudResult> {
    const body: ContactOtpRequest = { kind: kind, value: value };
    return this.parseResult(await this.authenticatedPost('/api/contact/otp/send', body, 20000));
  }

  public async updateContact(kind: string, value: string, verifyCode: string,
    challengeId: string): Promise<CloudResult> {
    const body: ContactUpdateRequest = {
      kind: kind,
      value: value,
      verifyCode: verifyCode,
      challengeId: challengeId,
    };
    const result = this.parseResult(await this.authenticatedPost('/api/contact/update', body, 20000));
    if (result.success && (
      (kind === 'phone' && /^1[3-9]\d{9}$/.test(this.sessionUserKey))
      || (kind === 'email' && this.sessionUserKey.indexOf('@') > 0)
    )) {
      this.sessionUserKey = value;
      if (this.rememberSession) await this.persistSession();
    }
    return result;
  }

  public async uploadAvatar(imageBase64: string): Promise<CloudResult> {
    const body: AvatarUploadRequest = { imageBase64: imageBase64, mimeType: 'image/jpeg' };
    return this.parseResult(await this.authenticatedPost('/api/avatar', body, 20000));
  }

  public async downloadAvatar(): Promise<CloudResult> {
    return this.parseResult(
      await this.requestRaw('/api/avatar', http.RequestMethod.GET, new EmptyRequest(), true, 20000, true)
    );
  }

  public async changePassword(oldPasswordHash: string, newPasswordHash: string): Promise<CloudResult> {
    const body: ChangePasswordRequest = {
      oldPasswordHash: oldPasswordHash,
      newPasswordHash: newPasswordHash,
    };
    const result = this.parseResult(await this.authenticatedPost('/api/changePassword', body));
    if (result.success) {
      this.clearSession();
      await this.clearPersistedSession();
    }
    return result;
  }

  public async deleteUser(passwordHash: string): Promise<CloudResult> {
    const body: DeleteUserRequest = { passwordHash: passwordHash };
    const result = this.parseResult(await this.authenticatedPost('/api/deleteUser', body));
    if (result.success) {
      this.clearSession();
      await this.clearPersistedSession();
    }
    return result;
  }
}
