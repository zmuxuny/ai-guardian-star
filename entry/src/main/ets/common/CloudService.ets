/** 云端账号与内存会话。Token 不落盘、不写日志。 */
import http from '@ohos.net.http';
import { ECS_BASE_URL } from '../config';

export interface CloudUser {
  username: string;
  nickname: string;
  phone: string;
  avatarPath: string;
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

interface ChangePasswordRequest {
  oldPasswordHash: string;
  newPasswordHash: string;
}

interface DeleteUserRequest {
  passwordHash: string;
}

interface AllowedProfileUpdate {
  nickname?: string;
  avatarPath?: string;
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
  private accessToken: string = '';
  private refreshToken: string = '';
  private sessionUserKey: string = '';
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
        return true;
      }
    } catch (_e) {}
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

  public async login(username: string, passwordHash: string): Promise<CloudResult> {
    this.clearSession();
    const body: LoginRequest = { username: username, passwordHash: passwordHash };
    const result = this.parseResult(
      await this.requestRaw('/api/login', http.RequestMethod.POST, body, false, 10000, false)
    );
    if (result.success && result.accessToken && result.refreshToken) {
      this.accessToken = result.accessToken;
      this.refreshToken = result.refreshToken;
      this.sessionUserKey = username;
      return result;
    }
    if (result.success) {
      return { success: false, message: '服务器未返回有效会话' };
    }
    return result;
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
    }
  }

  public async updateUser(fields: CloudUpdateFields): Promise<CloudResult> {
    const body: AllowedProfileUpdate = {};
    if (fields.nickname !== '') body.nickname = fields.nickname;
    if (fields.avatarPath !== '') body.avatarPath = fields.avatarPath;
    if (fields.address !== '') body.address = fields.address;
    return this.parseResult(await this.authenticatedPost('/api/updateUser', body));
  }

  public async changePassword(oldPasswordHash: string, newPasswordHash: string): Promise<CloudResult> {
    const body: ChangePasswordRequest = {
      oldPasswordHash: oldPasswordHash,
      newPasswordHash: newPasswordHash,
    };
    const result = this.parseResult(await this.authenticatedPost('/api/changePassword', body));
    if (result.success) this.clearSession();
    return result;
  }

  public async deleteUser(passwordHash: string): Promise<CloudResult> {
    const body: DeleteUserRequest = { passwordHash: passwordHash };
    const result = this.parseResult(await this.authenticatedPost('/api/deleteUser', body));
    if (result.success) this.clearSession();
    return result;
  }
}
