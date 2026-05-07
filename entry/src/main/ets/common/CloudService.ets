/**
 * CloudService.ets — 云端账号 REST API 封装
 *
 * 对应 ECS Flask 接口：
 *   POST /api/register   注册
 *   POST /api/login      登录验证 + 拉取用户信息
 *   POST /api/updateUser 更新昵称/头像路径
 *
 * 设计原则：
 *   - 本地 RDB 是主库，云端是备份/跨设备恢复用
 *   - 所有接口失败时静默降级，不阻塞本地流程
 *   - App 侧永远先操作本地，再异步同步云端
 */
import http from '@ohos.net.http';
import { ECS_BASE_URL } from '../config';

// ── 接口数据结构 ──────────────────────────────────────────────

export interface CloudUser {
  username: string;
  nickname: string;
  phone: string;
  passwordHash: string;
  avatarPath: string;
  email: string;
  address: string;
  createTime: number;
}

export interface CloudResult {
  success: boolean;
  message: string;
  user?: CloudUser;
}

interface LoginRequest {
  username: string;
  passwordHash: string;
}

interface SendCodeRequest {
  target: string;
  type: string;
  username: string;
}

interface VerifyCodeRequest {
  target: string;
  code: string;
  username: string;
}

interface ChangePasswordRequest {
  username: string;
  oldPasswordHash: string;
  newPasswordHash: string;
}

/** 更新资料时传给云端的字段（全部可选，用显式 class 替代 Partial） */
export class CloudUpdateFields {
  username: string = '';
  nickname: string = '';
  avatarPath: string = '';
  phone: string = '';
  email: string = '';
  address: string = '';
  passwordHash: string = '';
}

// ── 核心请求工具 ──────────────────────────────────────────────

async function postJson(path: string, body: Object): Promise<CloudResult> {
  const req = http.createHttp();
  try {
    const bodyStr = JSON.stringify(body);
    console.info('[CloudService]: POST', path, 'body:', bodyStr);
    const resp = await req.request(ECS_BASE_URL + path, {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: bodyStr,
      connectTimeout: 10000,
      readTimeout: 10000,
    });

    const resultStr = resp.result as string;
    console.info('[CloudService]: 响应', path, 'status:', resp.responseCode, 'body:', resultStr);

    try {
      const result = JSON.parse(resultStr) as CloudResult;
      console.info('[CloudService]: 解析成功', path, 'success:', result.success);
      return result;
    } catch (parseError) {
      console.error('[CloudService]: JSON解析失败', path, '响应内容:', resultStr.substring(0, 200));
      return { success: false, message: '服务器响应格式错误' };
    }
  } catch (e) {
    console.error('[CloudService]: 请求失败', path, '错误详情:', JSON.stringify(e));
    return { success: false, message: '网络不可用' };
  } finally {
    req.destroy();
  }
}

// ── 对外 API ──────────────────────────────────────────────────

export class CloudService {
  private static instance: CloudService;

  public static getInstance(): CloudService {
    if (!CloudService.instance) {
      CloudService.instance = new CloudService();
    }
    return CloudService.instance;
  }

  /** 注册新账号到云端，失败不影响本地 */
  async register(user: CloudUser): Promise<CloudResult> {
    return postJson('/api/register', user);
  }

  /** 云端验证账号 + 拉取用户信息（换新手机时用） */
  async login(username: string, passwordHash: string): Promise<CloudResult> {
    const body: LoginRequest = { username: username, passwordHash: passwordHash };
    return postJson('/api/login', body);
  }

  /** 更新云端用户资料，只传需要更新的字段 */
  async updateUser(fields: CloudUpdateFields): Promise<CloudResult> {
    return postJson('/api/updateUser', fields);
  }

  /** 发送验证码到手机或邮箱 */
  async sendVerificationCode(target: string, type: string, username: string): Promise<CloudResult> {
    const body: SendCodeRequest = { target: target, type: type, username: username };
    return postJson('/api/sendCode', body);
  }

  /** 验证验证码 */
  async verifyCode(target: string, code: string, username: string): Promise<CloudResult> {
    const body: VerifyCodeRequest = { target: target, code: code, username: username };
    return postJson('/api/verifyCode', body);
  }

  /** 修改密码 */
  async changePassword(username: string, oldPasswordHash: string, newPasswordHash: string): Promise<CloudResult> {
    const body: ChangePasswordRequest = { username: username, oldPasswordHash: oldPasswordHash, newPasswordHash: newPasswordHash };
    return postJson('/api/changePassword', body);
  }
}
