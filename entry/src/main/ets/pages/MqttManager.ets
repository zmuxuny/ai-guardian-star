import {
  MqttAsync,
  MqttClient,
  MqttClientOptions,
  MqttConnectOptions,
  MqttMessage,
  MqttResponse,
} from "@ohos/mqtt";
import { DatabaseHelper, HealthEvent } from "../database/DatabaseHelper";
import { UserManager } from "../common/UserManager";
import { BROKER_URL, ALERT_TOPIC, MQTT_CA_CERT } from '../config';
import { parseAlert, EventType, payloadToString } from '../common/MqttParser';
import { CloudService } from '../common/CloudService';

export interface FallRecord {
  time: string;
  date: string;
  timestamp: number;
}

export interface SedentaryRecord {
  time: string;
  date: string;
  timestamp: number;
}

export interface CacheStats {
  fallCount: number;
  sedentaryCount: number;
  oldestFallRecord: string;
  newestFallRecord: string;
  oldestSedentaryRecord: string;
  newestSedentaryRecord: string;
}

@Observed
export class MqttManager {
  private static instance: MqttManager;
  private mqttClient: MqttClient | null = null;

  @Track public isConnected: boolean = false;
  @Track public deviceOnline: boolean = false; // 开发板是否在线（20秒超时）
  @Track public latestMessage: string = "正在启动...";
  @Track public isFallDetected: boolean = false;
  @Track public fallTimestamp: number = 0;
  @Track public fallRecords: FallRecord[] = [];
  @Track public isSedentaryDetected: boolean = false;
  @Track public sedentaryTimestamp: number = 0;
  @Track public sedentaryRecords: SedentaryRecord[] = [];
  @Track public isStrangerDetected: boolean = false;
  @Track public strangerTimestamp: number = 0;

  private fallRecoveryTimer: number = -1;
  private sedentaryRecoveryTimer: number = -1;
  private strangerRecoveryTimer: number = -1;
  private readonly FALL_RECOVERY_DELAY: number = 3000;
  private readonly SEDENTARY_RECOVERY_DELAY: number = 3000;
  private readonly STRANGER_RECOVERY_DELAY: number = 5000;
  private lastRecordedFallTimestamp: number = 0;
  private lastRecordedSedentaryTimestamp: number = 0;
  private lastDeviceActivity: number = 0;
  private readonly DEVICE_TIMEOUT_MS: number = 20000; // 20秒无消息视为离线
  private deviceCheckTimer: number = -1; // 用于定期检查设备在线状态

  private reconnectTimer: number = -1;
  private renewalTimer: number = -1;
  private wantsConnection: boolean = false;
  private connecting: boolean = false;
  private connectionVersion: number = 0;

  private constructor() {
    CloudService.getInstance().setSessionClearedListener(() => {
      this.disconnect();
      this.clearAllCache();
    });
  }

  public static getInstance(): MqttManager {
    if (!MqttManager.instance) MqttManager.instance = new MqttManager();
    return MqttManager.instance;
  }

  private setupListeners(client: MqttClient): void {
    client.connectLost((_err: Error, _data: MqttResponse) => {
      if (this.mqttClient !== client) return;
      this.isConnected = false;
      this.latestMessage = "连接已断开";
      this.deviceOnline = false;
      this.stopDeviceCheck();
      this.clearFallRecoveryTimer();
      this.reconnect();
    });
    client.messageArrived((err: Error, data: MqttMessage) => {
      if (err || this.mqttClient !== client || !this.wantsConnection ||
        !CloudService.getInstance().hasSession()) return;
      this.handleMessage(data.topic, data.payload);
    });
  }

  public async testConnection(): Promise<boolean> {
    await this.connectAndSubscribe();
    return this.isConnected;
  }

  private clearConnectionTimers(): void {
    if (this.reconnectTimer !== -1) clearTimeout(this.reconnectTimer);
    if (this.renewalTimer !== -1) clearTimeout(this.renewalTimer);
    this.reconnectTimer = -1;
    this.renewalTimer = -1;
  }

  private async releaseClient(): Promise<void> {
    const client = this.mqttClient;
    this.mqttClient = null;
    this.isConnected = false;
    this.deviceOnline = false;
    this.stopDeviceCheck();
    if (client) {
      try { await client.disconnect(); } catch (_error) {}
      try { await client.destroy(); } catch (_error) {}
    }
  }

  public async disconnect(): Promise<void> {
    this.wantsConnection = false;
    this.connectionVersion++;
    this.connecting = false;
    this.clearConnectionTimers();
    this.clearFallRecoveryTimer();
    this.latestMessage = "未连接";
    await this.releaseClient();
  }

  public async connectAndSubscribe(topic: string = ALERT_TOPIC): Promise<void> {
    const cloud = CloudService.getInstance();
    if (!cloud.hasSession()) {
      await this.disconnect();
      this.latestMessage = "请先登录";
      return;
    }
    if (topic !== ALERT_TOPIC || this.connecting || this.isConnected) return;
    this.wantsConnection = true;
    this.connecting = true;
    this.clearConnectionTimers();
    const version = ++this.connectionVersion;
    try {
      await this.releaseClient();
      if (version !== this.connectionVersion) return;
      this.latestMessage = "正在连接...";
      const result = await cloud.getMqttCredentials();
      if (version !== this.connectionVersion || !this.wantsConnection || !cloud.hasSession()) return;
      const credentials = result.credentials;
      if (!result.success || !credentials) {
        this.latestMessage = result.message || "未能获取设备访问凭据";
        this.reconnect();
        return;
      }
      if (credentials.topic !== ALERT_TOPIC || !credentials.password || !credentials.username ||
        credentials.clientId !== credentials.username || !Number.isFinite(credentials.expiresIn) ||
        credentials.expiresIn <= 30) {
        throw new Error('无效设备访问凭据');
      }
      const clientOptions: MqttClientOptions = {
        url: BROKER_URL, clientId: credentials.clientId, persistenceType: 1,
      };
      const client = MqttAsync.createMqtt(clientOptions);
      this.mqttClient = client;
      this.setupListeners(client);
      const connectOptions: MqttConnectOptions = {
        connectTimeout: 30,
        keepAliveInterval: 60,
        cleanSession: true,
        userName: credentials.username,
        password: credentials.password,
        MQTTVersion: 4,
        sslOptions: {
          enableServerCertAuth: true,
          trustStoreContent: MQTT_CA_CERT,
          verify: true,
        },
      };
      const connected = await client.connect(connectOptions);
      if (version !== this.connectionVersion) return;
      if (connected.code !== 0) throw new Error('连接失败');
      const subscribed = await client.subscribe({ topic: credentials.topic, qos: 1 });
      if (version !== this.connectionVersion) return;
      if (subscribed.code !== 0) throw new Error('订阅失败');
      this.isConnected = true;
      this.lastDeviceActivity = 0;
      this.startDeviceCheck();
      this.latestMessage = "已连接";
      this.clearFallRecoveryTimer();
      this.isFallDetected = false;
      this.fallTimestamp = 0;
      this.renewalTimer = setTimeout(() => {
        this.renewalTimer = -1;
        this.isConnected = false;
        this.connectAndSubscribe();
      }, (credentials.expiresIn - 30) * 1000) as number;
    } catch (_error) {
      if (version !== this.connectionVersion) return;
      await this.releaseClient();
      this.latestMessage = "未连接";
      this.reconnect();
    } finally {
      if (version === this.connectionVersion) this.connecting = false;
    }
  }
  private clearFallRecoveryTimer(): void {
    if (this.fallRecoveryTimer !== -1) {
      clearTimeout(this.fallRecoveryTimer);
      this.fallRecoveryTimer = -1;
    }
  }

  /** 启动设备在线检测定时器（每5秒检查一次） */
  private startDeviceCheck(): void {
    this.stopDeviceCheck();
    this.deviceCheckTimer = setInterval(() => {
      if (!this.isConnected) {
        this.deviceOnline = false;
        return;
      }
      // 如果在DEVICE_TIMEOUT_MS内收到过设备消息，视为在线
      const elapsed = Date.now() - this.lastDeviceActivity;
      this.deviceOnline = (elapsed < this.DEVICE_TIMEOUT_MS);
    }, 5000) as number;
  }

  /** 停止设备在线检测定时器 */
  private stopDeviceCheck(): void {
    if (this.deviceCheckTimer !== -1) {
      clearInterval(this.deviceCheckTimer);
      this.deviceCheckTimer = -1;
    }
  }
  private startFallRecoveryTimer(): void {
    this.clearFallRecoveryTimer();
    this.fallRecoveryTimer = setTimeout(() => {
      this.isFallDetected = false;
      this.fallTimestamp = 0;
      this.latestMessage = `正常监测中`;
      this.fallRecoveryTimer = -1;
    }, this.FALL_RECOVERY_DELAY) as number;
  }
  private clearSedentaryRecoveryTimer(): void {
    if (this.sedentaryRecoveryTimer !== -1) {
      clearTimeout(this.sedentaryRecoveryTimer);
      this.sedentaryRecoveryTimer = -1;
    }
  }
  private startSedentaryRecoveryTimer(): void {
    this.clearSedentaryRecoveryTimer();
    this.sedentaryRecoveryTimer = setTimeout(() => {
      this.isSedentaryDetected = false;
      this.sedentaryTimestamp = 0;
      this.latestMessage = `正常监测中`;
      this.sedentaryRecoveryTimer = -1;
    }, this.FALL_RECOVERY_DELAY) as number;
  }
  private clearFallState(): void {
    this.isFallDetected = false;
    this.fallTimestamp = 0;
    this.clearFallRecoveryTimer();
  }
  private clearSedentaryState(): void {
    this.isSedentaryDetected = false;
    this.sedentaryTimestamp = 0;
    this.clearSedentaryRecoveryTimer();
  }
  private clearStrangerRecoveryTimer(): void {
    if (this.strangerRecoveryTimer !== -1) {
      clearTimeout(this.strangerRecoveryTimer);
      this.strangerRecoveryTimer = -1;
    }
  }
  private startStrangerRecoveryTimer(): void {
    this.clearStrangerRecoveryTimer();
    this.strangerRecoveryTimer = setTimeout(() => {
      this.isStrangerDetected = false;
      this.strangerTimestamp = 0;
      this.strangerRecoveryTimer = -1;
    }, this.STRANGER_RECOVERY_DELAY) as number;
  }
  private clearStrangerState(): void {
    this.isStrangerDetected = false;
    this.strangerTimestamp = 0;
    this.clearStrangerRecoveryTimer();
  }

  private padZero(num: number): string {
    return num < 10 ? `0${num}` : `${num}`;
  }

  private formatTimestamp(timestamp: number | undefined): string {
    const date = new Date();
    return (
      `${date.getFullYear()}-${this.padZero(date.getMonth() + 1)}-${this.padZero(date.getDate())} ` +
      `${this.padZero(date.getHours())}:${this.padZero(date.getMinutes())}:${this.padZero(date.getSeconds())}`
    );
  }

  private handleMessage(topic: string, payload: string | ArrayBuffer) {
    if (topic.startsWith('guardian/') || topic.startsWith('ai_guardian/')) {
      this.lastDeviceActivity = Date.now();
    }

    const content = payloadToString(payload);
    if (!content) {
      console.warn('[mqtt]: 解码失败:', topic);
      return;
    }

    const alert = parseAlert(content);
    if (alert.type === EventType.UNKNOWN) return;

    try {
      if (alert.type === EventType.FALL) {
        const currentTimestamp = Date.now();
        if (
          Date.now() - this.lastRecordedFallTimestamp > 2000 ||
          this.lastRecordedFallTimestamp === 0
        ) {
          this.addFallRecord(currentTimestamp);
          this.lastRecordedFallTimestamp = currentTimestamp;
        }
        this.isFallDetected = true;
        this.fallTimestamp = currentTimestamp;
        this.clearSedentaryState();
        this.latestMessage = `检测到跌倒`;
        this.startFallRecoveryTimer();
      } else if (alert.type === EventType.SEDENTARY) {
        const currentTimestamp = Date.now();
        if (
          Date.now() - this.lastRecordedSedentaryTimestamp > 2000 ||
          this.lastRecordedSedentaryTimestamp === 0
        ) {
          this.addSedentaryRecord(currentTimestamp);
          this.lastRecordedSedentaryTimestamp = currentTimestamp;
        }
        this.isSedentaryDetected = true;
        this.sedentaryTimestamp = currentTimestamp;
        this.clearFallState();
        this.latestMessage = `检测到久坐`;
        this.startSedentaryRecoveryTimer();
      } else if (alert.type === EventType.STRANGER) {
        this.isStrangerDetected = true;
        this.strangerTimestamp = Date.now();
        this.latestMessage = `检测到陌生人`;
        this.startStrangerRecoveryTimer();
      } else {
        this.clearFallState();
        this.clearSedentaryState();
        this.clearStrangerState();
        this.latestMessage = `正常监测中`;
      }
    } catch (_e) {
      // JSON 解析失败时尝试对原始文本做关键词兜底匹配
      const lower = content.toLowerCase();
      const isFall =
        (lower.includes("fall") || content.includes("跌倒")) &&
        !lower.includes("no fall") &&
        !lower.includes("normal") &&
        !lower.includes("sedentary");
      const isSedentary =
        (lower.includes("sedentary") || content.includes("久坐")) &&
        !lower.includes("normal");
      const isStranger = lower.includes("stranger");
      if (isFall) {
        const ts = Date.now();
        if (ts - this.lastRecordedFallTimestamp > 2000 || this.lastRecordedFallTimestamp === 0) {
          this.addFallRecord(ts);
          this.lastRecordedFallTimestamp = ts;
        }
        this.isFallDetected = true;
        this.fallTimestamp = ts;
        this.clearSedentaryState();
        this.latestMessage = `检测到跌倒`;
        this.startFallRecoveryTimer();
      } else if (isSedentary) {
        const ts = Date.now();
        if (
          ts - this.lastRecordedSedentaryTimestamp > 2000 ||
          this.lastRecordedSedentaryTimestamp === 0
        ) {
          this.addSedentaryRecord(ts);
          this.lastRecordedSedentaryTimestamp = ts;
        }
        this.isSedentaryDetected = true;
        this.sedentaryTimestamp = ts;
        this.clearFallState();
        this.latestMessage = `检测到久坐`;
        this.startSedentaryRecoveryTimer();
      } else if (isStranger) {
        this.isStrangerDetected = true;
        this.strangerTimestamp = Date.now();
        this.latestMessage = `检测到陌生人`;
        this.startStrangerRecoveryTimer();
      } else {
        this.clearFallState();
        this.clearSedentaryState();
        this.clearStrangerState();
        this.latestMessage = `正常监测中`;
      }
    }
  }

  private reconnect(): void {
    if (!this.wantsConnection || !CloudService.getInstance().hasSession() || this.reconnectTimer !== -1) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = -1;
      if (this.wantsConnection) this.connectAndSubscribe();
    }, 5000) as number;
  }
  // ── 关键改动：addFallRecord / addSedentaryRecord 新增持久化写库 ──

  /** 获取当前登录用户名（统一入口，保证一致性） */
  private getCurrentUsername(): string {
    return UserManager.getInstance().getCurrentUsername();
  }

  private addFallRecord(timestamp: number): void {
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth() + 1)}.${this.padZero(now.getDate())}`;
    const newRecord: FallRecord = { time: timeStr, date: dateStr, timestamp };
    this.fallRecords = [newRecord, ...this.fallRecords];
    const username = this.getCurrentUsername();
    console.log(
      `[mqtt]:✅ 摔倒记录已添加 ${dateStr} ${timeStr} (user=${username})，总计 ${this.fallRecords.length} 条`,
    );

    // ── 持久化到 ArkDB ────────────────────────────────────────
    const event: HealthEvent = {
      eventType: "fall",
      eventTime: timestamp,
      dateStr: dateStr,
      timeStr: timeStr,
      severity: 3,
      isHandled: 0,
      username: username,
    };
    DatabaseHelper.getInstance()
      .insertHealthEvent(event)
      .then((rowId) =>
        console.log(`[mqtt]:📦 ArkDB 写入摔倒事件成功 rowId=${rowId} (user=${username})`),
      )
      .catch((e: Error) => console.error(`[mqtt]:❌ ArkDB 写入摔倒事件失败 ${e.message}`));
  }

  private addSedentaryRecord(timestamp: number): void {
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth() + 1)}.${this.padZero(now.getDate())}`;
    const newRecord: SedentaryRecord = { time: timeStr, date: dateStr, timestamp };
    this.sedentaryRecords = [newRecord, ...this.sedentaryRecords];
    const username = this.getCurrentUsername();
    console.log(
      `[mqtt]:✅ 久坐记录已添加 ${dateStr} ${timeStr} (user=${username})，总计 ${this.sedentaryRecords.length} 条`,
    );

    // ── 持久化到 ArkDB ────────────────────────────────────────
    const event: HealthEvent = {
      eventType: "sedentary",
      eventTime: timestamp,
      dateStr: dateStr,
      timeStr: timeStr,
      severity: 1,
      isHandled: 0,
      username: username,
    };
    DatabaseHelper.getInstance()
      .insertHealthEvent(event)
      .then((rowId) =>
        console.log(`[mqtt]:📦 ArkDB 写入久坐事件成功 rowId=${rowId} (user=${username})`),
      )
      .catch((e: Error) => console.error(`[mqtt]:❌ ArkDB 写入久坐事件失败 ${e.message}`));
  }

  // ── 缓存管理（清内存 + 同步清库）──────────────────────────────

  public clearFallRecords(): void {
    this.fallRecords = [];
    this.lastRecordedFallTimestamp = 0;
    DatabaseHelper.getInstance()
      .clearAllHealthEvents()
      .then(() => console.log("[mqtt]:ArkDB 摔倒/久坐历史已清除"))
      .catch((e: Error) => console.error(`[mqtt]:ArkDB 清除失败 ${e.message}`));
  }

  public resetMqttState(): void {
    this.isFallDetected = false;
    this.fallTimestamp = 0;
    this.isSedentaryDetected = false;
    this.sedentaryTimestamp = 0;
    this.isStrangerDetected = false;
    this.strangerTimestamp = 0;
    this.latestMessage = "正常监测中";
    this.clearFallRecoveryTimer();
    this.clearSedentaryRecoveryTimer();
    this.clearStrangerRecoveryTimer();
  }

  public getCacheStats(): CacheStats {
    const fallCount = this.fallRecords.length;
    const sedentaryCount = this.sedentaryRecords.length;
    return {
      fallCount,
      sedentaryCount,
      oldestFallRecord:
        fallCount > 0
          ? `${this.fallRecords[fallCount - 1].date} ${this.fallRecords[fallCount - 1].time}`
          : "无",
      newestFallRecord:
        fallCount > 0 ? `${this.fallRecords[0].date} ${this.fallRecords[0].time}` : "无",
      oldestSedentaryRecord:
        sedentaryCount > 0
          ? `${this.sedentaryRecords[sedentaryCount - 1].date} ${this.sedentaryRecords[sedentaryCount - 1].time}`
          : "无",
      newestSedentaryRecord:
        sedentaryCount > 0
          ? `${this.sedentaryRecords[0].date} ${this.sedentaryRecords[0].time}`
          : "无",
    };
  }

  public clearAllCache(): void {
    this.fallRecords = [];
    this.sedentaryRecords = [];
    this.lastRecordedFallTimestamp = 0;
    this.lastRecordedSedentaryTimestamp = 0;
    this.resetMqttState();
    console.log("[mqtt]:✅ 所有缓存已清理完成");
  }
}
