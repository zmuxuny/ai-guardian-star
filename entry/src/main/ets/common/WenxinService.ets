/**
 * WenxinService.ets — 文心 AI 助手服务层
 *
 * 职责：封装与云端 Flask 中转服务的通信，构建带健康上下文的请求
 * 隐私原则：仅传脱敏统计摘要（次数/天数），不传手机号/人脸/原始事件详情
 */

import http from '@ohos.net.http';
import { MqttManager } from '../pages/MqttManager';
import { ECS_BASE_URL } from '../config';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface HealthContext {
  fallCount7d: number;
  sedentaryCount7d: number;
  lastFallDaysAgo: number;      // -1 表示没有记录
  deviceOnline: boolean;
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

    const httpRequest = http.createHttp();
    try {
      const response = await httpRequest.request(
        `${ECS_BASE_URL}/ai/chat`,
        {
          method: http.RequestMethod.POST,
          header: { 'Content-Type': 'application/json' },
          extraData: JSON.stringify(req),
          connectTimeout: 10000,
          readTimeout: 35000,   // 文心大模型首 token 可能较慢
        }
      );

      if (response.responseCode !== 200) {
        const errBody = response.result as string;
        console.error('[WenxinService] HTTP error:', response.responseCode, errBody);
        return `服务暂时不可用（${response.responseCode}），请稍后再试`;
      }

      const data = JSON.parse(response.result as string) as ChatResponse;
      return data.reply ?? '抱歉，AI 没有返回有效回复';

    } catch (e) {
      console.error('[WenxinService] request failed:', e);
      return '网络连接失败，请检查网络后重试';
    } finally {
      httpRequest.destroy();
    }
  }

  /**
   * 从 MqttManager 提取脱敏健康摘要
   * 只取统计数字，不含任何可识别个人身份的字段
   */
  private buildHealthContext(): HealthContext {
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
      const latestFall = falls[falls.length - 1];
      lastFallDaysAgo = Math.floor((now - latestFall.timestamp) / (24 * 60 * 60 * 1000));
    }

    return {
      fallCount7d,
      sedentaryCount7d,
      lastFallDaysAgo,
      deviceOnline: mqtt.isConnected,
    };
  }
}
