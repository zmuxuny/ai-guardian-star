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

const ECS_BASE = 'http://117.78.9.144:8899';

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

/** 登录请求体 */
class LoginBody {
  username: string = '';
  passwordHash: string = '';
}

// ── 核心请求工具 ──────────────────────────────────────────────

async function postJson(path: string, bodyStr: string): Promise<CloudResult> {
  const req = http.createHttp();
  try {
    console.info('[CloudService]: 开始请求', path, 'body长度:', bodyStr.length);
    const resp = await req.request(ECS_BASE + path, {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: bodyStr,
      connectTimeout: 10000,  // 增加到10秒
      readTimeout: 10000,     // 增加到10秒
    });
    
    const resultStr = resp.result as string;
    console.info('[CloudService]: 请求成功', path, '响应长度:', resultStr.length);
    
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
    return { success: false, message: `网络请求失败: ${e.message || '未知错误'}` };
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
    return postJson('/api/register', JSON.stringify(user));
  }

  /** 云端验证账号 + 拉取用户信息（换新手机时用） */
  async login(username: string, passwordHash: string): Promise<CloudResult> {
    const body = new LoginBody();
    body.username = username;
    body.passwordHash = passwordHash;
    return postJson('/api/login', JSON.stringify(body));
  }

  /** 更新云端用户资料，只传需要更新的字段 */
  async updateUser(fields: CloudUpdateFields): Promise<CloudResult> {
    return postJson('/api/updateUser', JSON.stringify(fields));
  }
}
