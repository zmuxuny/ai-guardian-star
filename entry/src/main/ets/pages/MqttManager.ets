import {
  MqttAsync,
  MqttClient,
  MqttClientOptions,
  MqttConnectOptions,
  MqttMessage,
  MqttResponse,
  MqttSubscribeOptions
} from '@ohos/mqtt';
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';

// 定义 JSON 消息的接口（匹配 Python 代码发送的 MQTT 消息格式）
interface AlertData {
  device_id: string;
  event: string;
  confidence: number;
  timestamp: number;
  datetime: string;
}
interface AlertLike {
  device_id?: string;
  event?: string;
  alert_type?: string;
  type?: string;
  confidence?: number;
  timestamp?: number;
  datetime?: string;
}

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

const BROKER_HOST = '192.168.5.192';
const BROKER_PORT = 1883;
const BROKER_URL = `tcp://${BROKER_HOST}:${BROKER_PORT}`;
const ALERT_TOPIC = 'ai_guardian/alerts/#';

@Observed
export class MqttManager {
  private static instance: MqttManager;
  private mqttClient: MqttClient | null = null;

  @Track public isConnected: boolean = false;
  @Track public latestMessage: string = '正在启动...';
  @Track public isFallDetected: boolean = false;
  @Track public fallTimestamp: number = 0;
  @Track public fallRecords: FallRecord[] = [];
  @Track public isSedentaryDetected: boolean = false;
  @Track public sedentaryTimestamp: number = 0;
  @Track public sedentaryRecords: SedentaryRecord[] = [];

  private fallRecoveryTimer: number = -1;
  private sedentaryRecoveryTimer: number = -1;
  private readonly FALL_RECOVERY_DELAY: number = 3000;
  private readonly SEDENTARY_RECOVERY_DELAY: number = 3000;
  private lastRecordedFallTimestamp: number = 0;
  private lastRecordedSedentaryTimestamp: number = 0;

  private constructor() { this.initClient(); }

  public static getInstance(): MqttManager {
    if (!MqttManager.instance) MqttManager.instance = new MqttManager();
    return MqttManager.instance;
  }

  private initClient() {
    const clientId = `HarmonyOS_Client_sad`;
    const clientOptions: MqttClientOptions = {
      url: BROKER_URL, clientId: clientId, persistenceType: 1,
    };
    try {
      this.mqttClient = MqttAsync.createMqtt(clientOptions);
      this.setupListeners(this.mqttClient);
      console.log('[mqtt]:MQTT 客户端初始化成功。');
    } catch (e) {
      console.error('[mqtt]:MQTT 客户端初始化失败:', e);
      this.latestMessage = `连接异常`;
    }
  }

  private setupListeners(client: MqttClient) {
    client.connectLost((err: Error, data: MqttResponse) => {
      this.isConnected = false;
      console.error('[mqtt]:MQTT 连接丢失:', err, data);
      this.latestMessage = `连接已断开`;
      this.clearFallRecoveryTimer();
      this.reconnect();
    });
    client.messageArrived((err: Error, data: MqttMessage) => {
      if (err) { console.error('[mqtt]:接收消息错误:', err); return; }
      console.log(`[mqtt]:💬 messageArrived 回调触发! topic=${data.topic}`);
      this.handleMessage(data.topic, data.payload);
    });
  }

  public async testConnection(): Promise<boolean> {
    try {
      if (!this.mqttClient) return false;
      const connectOptions: MqttConnectOptions = {
        connectTimeout: 10, keepAliveInterval: 30, cleanSession: true,
        userName: "", password: "", MQTTVersion: 4,
      };
      const result = await this.mqttClient.connect(connectOptions);
      if (result.code === 0) { await this.mqttClient.disconnect(); return true; }
      return false;
    } catch (error) { console.error('[mqtt]:连接测试失败:', error); return false; }
  }

  public async disconnect(): Promise<void> {
    if (this.mqttClient && this.isConnected) {
      try {
        await this.mqttClient.disconnect();
        this.isConnected = false;
        this.latestMessage = '未连接';
        this.clearFallRecoveryTimer();
      } catch (error) { console.error('[mqtt]:断开连接失败:', error); }
    }
  }

  public async connectAndSubscribe(topic: string = ALERT_TOPIC) {
    if (!this.mqttClient) {
      this.initClient();
      if (!this.mqttClient) {
        this.latestMessage = '连接异常'; return;
      }
    }
    const connectOptions: MqttConnectOptions = {
      connectTimeout: 30, keepAliveInterval: 60, cleanSession: true,
      userName: "", password: "", MQTTVersion: 4,
    };
    try {
      this.latestMessage = '正在连接...';
      const connectResult = await this.mqttClient.connect(connectOptions);
      if (connectResult.code !== 0) throw new Error(`连接失败，返回码: ${connectResult.code}`);
      this.isConnected = true;
      const subscribeResult = await this.mqttClient.subscribe({ topic: topic, qos: 1 });
      if (subscribeResult.code !== 0) throw new Error(`订阅失败，返回码: ${subscribeResult.code}`);
      this.latestMessage = `已连接`;
      this.clearFallRecoveryTimer(); this.isFallDetected = false; this.fallTimestamp = 0;
    } catch (err) {
      this.isConnected = false;
      this.latestMessage = `未连接`;
      this.reconnect();
    }
  }

  private clearFallRecoveryTimer(): void {
    if (this.fallRecoveryTimer !== -1) { clearTimeout(this.fallRecoveryTimer); this.fallRecoveryTimer = -1; }
  }
  private startFallRecoveryTimer(): void {
    this.clearFallRecoveryTimer();
    this.fallRecoveryTimer = setTimeout(() => {
      this.isFallDetected = false; this.fallTimestamp = 0;
      this.latestMessage = `正常监测中`;
      this.fallRecoveryTimer = -1;
    }, this.FALL_RECOVERY_DELAY) as number;
  }
  private clearSedentaryRecoveryTimer(): void {
    if (this.sedentaryRecoveryTimer !== -1) { clearTimeout(this.sedentaryRecoveryTimer); this.sedentaryRecoveryTimer = -1; }
  }
  private startSedentaryRecoveryTimer(): void {
    this.clearSedentaryRecoveryTimer();
    this.sedentaryRecoveryTimer = setTimeout(() => {
      this.isSedentaryDetected = false; this.sedentaryTimestamp = 0;
      this.latestMessage = `正常监测中`;
      this.sedentaryRecoveryTimer = -1;
    }, this.FALL_RECOVERY_DELAY) as number;
  }
  private clearFallState(): void {
    this.isFallDetected = false; this.fallTimestamp = 0; this.clearFallRecoveryTimer();
  }
  private clearSedentaryState(): void {
    this.isSedentaryDetected = false; this.sedentaryTimestamp = 0; this.clearSedentaryRecoveryTimer();
  }

  private padZero(num: number): string { return num < 10 ? `0${num}` : `${num}`; }

  private formatTimestamp(timestamp: number | undefined): string {
    const date = new Date();
    return `${date.getFullYear()}-${this.padZero(date.getMonth()+1)}-${this.padZero(date.getDate())} ` +
      `${this.padZero(date.getHours())}:${this.padZero(date.getMinutes())}:${this.padZero(date.getSeconds())}`;
  }

  private handleMessage(topic: string, payload: string | ArrayBuffer) {
    let messageContent: string = '';
    if (typeof payload !== 'string') {
      try {
        const uint8Array: Uint8Array = new Uint8Array(payload as ArrayBuffer);
        let charCodes: number[] = [];
        for (let i = 0; i < uint8Array.length; i++) charCodes.push(uint8Array[i]);
        messageContent = String.fromCharCode(...charCodes);
      } catch (e) { messageContent = `收到原始数据，但解码失败: ${topic}`; }
    } else { messageContent = payload; }

    try {
      const data = JSON.parse(messageContent) as AlertLike;
      const eventField = (data.event ?? data.alert_type ?? data.type ?? '') as string;
      const rawEvent: string = String(eventField).toLowerCase().trim();
      const isEmpty = rawEvent === '' || rawEvent === 'null' || rawEvent === 'none';
      const hasFallKeyword = rawEvent.includes('fall') || rawEvent.includes('跌倒');
      const hasSedentaryKeyword = rawEvent.includes('sedentary') || rawEvent.includes('久坐') || rawEvent.includes('sitting_long');
      const hasNormalKeyword = rawEvent.includes('no fall') || rawEvent.includes('normal') || rawEvent.includes('stand') || rawEvent.includes('walk');
      const isFall: boolean = !isEmpty && hasFallKeyword && !hasNormalKeyword && !hasSedentaryKeyword;
      const isSedentary: boolean = !isEmpty && hasSedentaryKeyword && !hasNormalKeyword;

      if (isFall) {
        const currentTimestamp = Date.now();
        if (Date.now() - this.lastRecordedFallTimestamp > 2000 || this.lastRecordedFallTimestamp === 0) {
          this.addFallRecord(currentTimestamp);
          this.lastRecordedFallTimestamp = currentTimestamp;
        }
        this.isFallDetected = true; this.fallTimestamp = currentTimestamp;
        this.clearSedentaryState();
        this.latestMessage = `检测到跌倒`;
        this.startFallRecoveryTimer();
      } else if (isSedentary) {
        const currentTimestamp = Date.now();
        if (Date.now() - this.lastRecordedSedentaryTimestamp > 2000 || this.lastRecordedSedentaryTimestamp === 0) {
          this.addSedentaryRecord(currentTimestamp);
          this.lastRecordedSedentaryTimestamp = currentTimestamp;
        }
        this.isSedentaryDetected = true; this.sedentaryTimestamp = currentTimestamp;
        this.clearFallState();
        this.latestMessage = `检测到久坐`;
        this.startSedentaryRecoveryTimer();
      } else {
        this.clearFallState(); this.clearSedentaryState();
        this.latestMessage = `正常监测中`;
      }
    } catch (e) {
      const lower = messageContent.toLowerCase();
      const isFall = (lower.includes('fall') || messageContent.includes('跌倒')) &&
                     !lower.includes('no fall') && !lower.includes('normal') &&
                     !lower.includes('sedentary');
      const isSedentary = (lower.includes('sedentary') || messageContent.includes('久坐')) && !lower.includes('normal');
      if (isFall) {
        const ts = Date.now();
        if (ts - this.lastRecordedFallTimestamp > 2000 || this.lastRecordedFallTimestamp === 0) {
          this.addFallRecord(ts); this.lastRecordedFallTimestamp = ts;
        }
        this.isFallDetected = true; this.fallTimestamp = ts; this.clearSedentaryState();
        this.latestMessage = `检测到跌倒`;
        this.startFallRecoveryTimer();
      } else if (isSedentary) {
        const ts = Date.now();
        if (ts - this.lastRecordedSedentaryTimestamp > 2000 || this.lastRecordedSedentaryTimestamp === 0) {
          this.addSedentaryRecord(ts); this.lastRecordedSedentaryTimestamp = ts;
        }
        this.isSedentaryDetected = true; this.sedentaryTimestamp = ts; this.clearFallState();
        this.latestMessage = `检测到久坐`;
        this.startSedentaryRecoveryTimer();
      } else {
        this.clearFallState(); this.clearSedentaryState();
        this.latestMessage = `正常监测中`;
      }
    }
  }

  private async reconnect() {
    this.latestMessage = '正在重新连接...';
    setTimeout(() => { this.connectAndSubscribe(); }, 5000);
  }

  // ── 关键改动：addFallRecord / addSedentaryRecord 新增持久化写库 ──

  /** 获取当前登录用户名（统一入口，保证一致性） */
  private getCurrentUsername(): string {
    return AppStorage.get<string>('loggedInUsername') ?? 'default_user';
  }

  private addFallRecord(timestamp: number): void {
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth()+1)}.${this.padZero(now.getDate())}`;
    const newRecord: FallRecord = { time: timeStr, date: dateStr, timestamp };
    this.fallRecords = [newRecord, ...this.fallRecords];
    const username = this.getCurrentUsername();
    console.log(`[mqtt]:✅ 摔倒记录已添加 ${dateStr} ${timeStr} (user=${username})，总计 ${this.fallRecords.length} 条`);

    // ── 持久化到 ArkDB ────────────────────────────────────────
    const event: HealthEvent = {
      eventType: 'fall',
      eventTime: timestamp,
      dateStr:   dateStr,
      timeStr:   timeStr,
      severity:  3,
      isHandled: 0,
      username:  username,
    };
    DatabaseHelper.getInstance().insertHealthEvent(event)
      .then((rowId) => console.log(`[mqtt]:📦 ArkDB 写入摔倒事件成功 rowId=${rowId} (user=${username})`))
      .catch((e: Error) => console.error(`[mqtt]:❌ ArkDB 写入摔倒事件失败 ${e.message}`));
  }

  private addSedentaryRecord(timestamp: number): void {
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth()+1)}.${this.padZero(now.getDate())}`;
    const newRecord: SedentaryRecord = { time: timeStr, date: dateStr, timestamp };
    this.sedentaryRecords = [newRecord, ...this.sedentaryRecords];
    const username = this.getCurrentUsername();
    console.log(`[mqtt]:✅ 久坐记录已添加 ${dateStr} ${timeStr} (user=${username})，总计 ${this.sedentaryRecords.length} 条`);

    // ── 持久化到 ArkDB ────────────────────────────────────────
    const event: HealthEvent = {
      eventType: 'sedentary',
      eventTime: timestamp,
      dateStr:   dateStr,
      timeStr:   timeStr,
      severity:  1,
      isHandled: 0,
      username:  username,
    };
    DatabaseHelper.getInstance().insertHealthEvent(event)
      .then((rowId) => console.log(`[mqtt]:📦 ArkDB 写入久坐事件成功 rowId=${rowId} (user=${username})`))
      .catch((e: Error) => console.error(`[mqtt]:❌ ArkDB 写入久坐事件失败 ${e.message}`));
  }

  // ── 缓存管理（清内存 + 同步清库）──────────────────────────────

  public clearFallRecords(): void {
    this.fallRecords = []; this.lastRecordedFallTimestamp = 0;
    DatabaseHelper.getInstance().clearAllHealthEvents()
      .then(() => console.log('[mqtt]:ArkDB 摔倒/久坐历史已清除'))
      .catch((e: Error) => console.error(`[mqtt]:ArkDB 清除失败 ${e.message}`));
  }

  public resetMqttState(): void {
    this.isFallDetected = false; this.fallTimestamp = 0;
    this.isSedentaryDetected = false; this.sedentaryTimestamp = 0;
    this.latestMessage = '正常监测中';
    this.clearFallRecoveryTimer(); this.clearSedentaryRecoveryTimer();
  }

  public getCacheStats(): CacheStats {
    const fallCount = this.fallRecords.length;
    const sedentaryCount = this.sedentaryRecords.length;
    return {
      fallCount, sedentaryCount,
      oldestFallRecord: fallCount > 0 ? `${this.fallRecords[fallCount-1].date} ${this.fallRecords[fallCount-1].time}` : '无',
      newestFallRecord: fallCount > 0 ? `${this.fallRecords[0].date} ${this.fallRecords[0].time}` : '无',
      oldestSedentaryRecord: sedentaryCount > 0 ? `${this.sedentaryRecords[sedentaryCount-1].date} ${this.sedentaryRecords[sedentaryCount-1].time}` : '无',
      newestSedentaryRecord: sedentaryCount > 0 ? `${this.sedentaryRecords[0].date} ${this.sedentaryRecords[0].time}` : '无',
    };
  }

  public clearAllCache(): void {
    this.fallRecords = []; this.sedentaryRecords = [];
    this.lastRecordedFallTimestamp = 0; this.lastRecordedSedentaryTimestamp = 0;
    this.resetMqttState();
    console.log('[mqtt]:✅ 所有缓存已清理完成');
  }
}
