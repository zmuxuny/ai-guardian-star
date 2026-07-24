/**
 * WenxinService.ets — 文心 AI 助手服务层
 *
 * 职责：封装与云端 Flask 中转服务的通信，构建带健康上下文的请求
 * 隐私原则：按用户选择裁剪上下文，不传手机号、人脸等身份数据
 */

import { MqttManager } from '../pages/MqttManager';
import { STORE_KEY_AI_ACCESS_LEVEL } from '../config';
import { CloudService } from './CloudService';

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
    const context = this.buildHealthContext();
    const req: ChatRequest = {
      message: userMessage,
      history: history.slice(-20),   // 最多10轮，防止 payload 太大
      context: context,
    };

    try {
      const response = await CloudService.getInstance().authenticatedPost('/ai/chat', req, 35000);

      if (response.responseCode !== 200) {
        console.error('[WenxinService] HTTP error:', response.responseCode);
        return `服务暂时不可用（${response.responseCode}），请稍后再试`;
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

    const fallCount7d = falls.filter(r => r.timestamp >= sevenDaysAgo).length;
    const sedentaryCount7d = sedentaries.filter(r => r.timestamp >= sevenDaysAgo).length;

    // 最近一次摔倒距今天数（脱敏：只传天数，不传具体时间）
    let lastFallDaysAgo = -1;
    if (falls.length > 0) {
      const latestFall = falls[0];
      lastFallDaysAgo = Math.floor((now - latestFall.timestamp) / (24 * 60 * 60 * 1000));
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
      context.currentStatus = mqtt.latestMessage;
      context.latestFallRecord = falls.length > 0 ? `${falls[0].date} ${falls[0].time}` : '';
      context.latestSedentaryRecord = sedentaries.length > 0
        ? `${sedentaries[0].date} ${sedentaries[0].time}` : '';
    }
    return context;
  }
}
