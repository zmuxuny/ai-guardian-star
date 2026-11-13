/**
 * WenxinService.ets — 文心 AI 助手服务层
 *
 * 职责：封装与云端 Flask 中转服务的通信，构建带健康上下文的请求
 * 隐私原则：按用户选择裁剪上下文，不传手机号、人脸等身份数据
 */

import { MqttManager } from '../pages/MqttManager';
import { STORE_KEY_AI_ACCESS_LEVEL, STORE_KEY_AI_POLICY_STAMP } from '../config';
import { CloudService } from './CloudService';
import { AiPermissionService } from './AiPermissionService';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface HealthContext {
  accessLevel: string;
  fallCount7d?: number;
  sedentaryCount7d?: number;
  lastFallDaysAgo?: number;
  deviceOnline?: boolean;
  deviceConnected?: boolean;
  currentStatus?: string;
  latestFallRecord?: string;
  latestSedentaryRecord?: string;
}

export interface ChatRequest {
  message: string;
  history: ChatMessage[];
  context: HealthContext;
  policyVersion: number;
}

interface ChatError { error?: string; }

export function redactAiText(text: string): string {
  return text.replace(/(?<![A-Za-z0-9])[1-9]\d{16}[0-9Xx](?![A-Za-z0-9])/g, '[身份证号已隐藏]')
    .replace(/(?<!\d)(?:\+?86[ -]?)?1[3-9](?:[ -]?\d){9}(?!\d)/g, '[手机号已隐藏]')
    .replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g, '[邮箱已隐藏]');
}

export interface ChatResponse {
  reply: string;
  model: string;
  timestamp: number;
}

export class WenxinService {
  private static instance: WenxinService;

  private constructor() {}

  public static getInstance(): WenxinService {
    if (!WenxinService.instance) {
      WenxinService.instance = new WenxinService();
    }
    return WenxinService.instance;
  }

  /**
   * 发送聊天消息并获取 AI 回复
   * @param userMessage 用户输入的消息
   * @param history 历史对话（最多传最近10轮）
   * @returns AI 回复文本，失败时返回错误提示
   */
  public async chat(userMessage: string, history: ChatMessage[]): Promise<string> {
    const permissions = AiPermissionService.getInstance();
    const initialPolicy = permissions.current();
    if (!initialPolicy?.enabled) return 'AI 已关闭或权限未同步，请在个人中心检查';
    const originalStamp = AppStorage.get<string>(STORE_KEY_AI_POLICY_STAMP);
    const owner = CloudService.getInstance().getSessionUserKey();
    if (!await permissions.sync()) return '无法同步 AI 权限，请联网后重试';
    const policy = permissions.current();
    if (!policy?.enabled || originalStamp !== AppStorage.get<string>(STORE_KEY_AI_POLICY_STAMP)) {
      return 'AI 权限已变化，请重新提问';
    }
    const context = this.buildHealthContext();
    const safeHistory: ChatMessage[] = [];
    let historyLength = 0;
    for (let i = history.length - 1; i >= Math.max(0, history.length - 20); i--) {
      const content = redactAiText(history[i].content).slice(0, 2000);
      if (historyLength + content.length > 16000) break;
      historyLength += content.length;
      safeHistory.unshift({ role: history[i].role, content });
    }
    const req: ChatRequest = {
      message: redactAiText(userMessage),
      history: safeHistory,
      context: context,
      policyVersion: policy.version,
    };

    try {
      const response = await CloudService.getInstance().authenticatedPost('/ai/chat', req, 35000);
      const latest = permissions.current();
      if (!latest?.enabled || latest.version !== policy.version || owner !== CloudService.getInstance().getSessionUserKey()) {
        return '权限已变化，本次回复已丢弃';
      }

      if (response.responseCode !== 200) {
        console.error('[WenxinService] HTTP error:', response.responseCode);
        if (response.responseCode === 403 || response.responseCode === 409) await permissions.sync();
        const error = JSON.parse(response.result) as ChatError;
        return error.error || `服务暂时不可用（${response.responseCode}），请稍后再试`;
      }

      const data = JSON.parse(response.result) as ChatResponse;
      return data.reply ?? '抱歉，AI 没有返回有效回复';

    } catch (e) {
      console.error('[WenxinService] request failed');
      return '网络连接失败，请检查网络后重试';
    }
  }

  /** 从 MqttManager 按用户选择提取监护上下文。 */
  private buildHealthContext(): HealthContext {
    const savedAccessLevel = AppStorage.get<string>(STORE_KEY_AI_ACCESS_LEVEL);
    const accessLevel = savedAccessLevel === 'full' || savedAccessLevel === 'basic'
      ? savedAccessLevel : 'privacy';
    if (accessLevel === 'basic') {
      return { accessLevel: accessLevel };
    }

    const mqtt = MqttManager.getInstance();
    const falls = mqtt.fallRecords;
    const sedentaries = mqtt.sedentaryRecords;

    // 计算近7天的统计
    const now = Date.now();
    const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;

    const fallCount7d = falls.filter(r => r.timestamp >= sevenDaysAgo && r.timestamp <= now).length;
    const sedentaryCount7d = sedentaries.filter(r => r.timestamp >= sevenDaysAgo && r.timestamp <= now).length;

    // 最近一次摔倒距今天数（脱敏：只传天数，不传具体时间）
    let lastFallDaysAgo = -1;
    if (falls.length > 0) {
      const latestFall = falls[0];
      lastFallDaysAgo = Math.max(0, Math.min(36500, Math.floor((now - latestFall.timestamp) / (24 * 60 * 60 * 1000))));
    }

    const context: HealthContext = {
      accessLevel,
      fallCount7d,
      sedentaryCount7d,
      lastFallDaysAgo,
      deviceOnline: mqtt.deviceOnline,
    };
    if (accessLevel === 'full') {
      context.deviceConnected = mqtt.isConnected;
      context.currentStatus = redactAiText(mqtt.latestMessage).slice(0, 500);
      context.latestFallRecord = falls.length > 0 ? `${falls[0].date} ${falls[0].time}` : '';
      context.latestSedentaryRecord = sedentaries.length > 0
        ? `${sedentaries[0].date} ${sedentaries[0].time}` : '';
    }
    return context;
  }
}
