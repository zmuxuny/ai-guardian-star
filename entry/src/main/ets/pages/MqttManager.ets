import {
  MqttAsync,
  MqttClient,
  MqttClientOptions,
  MqttConnectOptions,
  MqttMessage,
  MqttResponse,
  MqttSubscribeOptions
} from '@ohos/mqtt';

// 定义 JSON 消息的接口（匹配 Python 代码发送的 MQTT 消息格式）
interface AlertData {
  device_id: string;
  event: string;
  confidence: number;
  timestamp: number;  // Python 中为秒级时间戳，需要乘以 1000 转为毫秒
  datetime: string;
}
// 兼容不同后端字段命名的扩展告警类型
interface AlertLike {
  device_id?: string;
  event?: string;
  alert_type?: string;
  type?: string;
  confidence?: number;
  timestamp?: number;
  datetime?: string;
}
// 摔倒记录数据接口
export interface FallRecord {
  time: string;        // 时间字符串，格式：HH:mm:ss
  date: string;        // 日期字符串，格式：YYYY.MM.DD
  timestamp: number;   // 时间戳，用于排序
}

// 久坐记录数据接口
export interface SedentaryRecord {
  time: string;        // 时间字符串，格式：HH:mm:ss
  date: string;        // 日期字符串，格式：YYYY.MM.DD
  timestamp: number;   // 时间戳，用于排序
}

// 缓存统计信息接口
export interface CacheStats {
  fallCount: number;
  sedentaryCount: number;
  oldestFallRecord: string;
  newestFallRecord: string;
  oldestSedentaryRecord: string;
  newestSedentaryRecord: string;
}

//昇腾开发板ip:192.168.137.100
// 【!!! 重要配置: 替换为您开发板的实际 IP 地址 (192.168.43.147) !!!】
// 这里的 IP 必须是 Broker 所在的开发板的 IP
const BROKER_HOST = '192.168.137.100';
// const BROKER_HOST = '192.168.5.118';
const BROKER_PORT = 1883;
const BROKER_URL = `tcp://${BROKER_HOST}:${BROKER_PORT}`;  // 修改：使用 tcp:// 前缀，匹配 HarmonyOS MQTT 库要求
const ALERT_TOPIC = 'ai_guardian/alerts/#';

@Observed
export class MqttManager {
  private static instance: MqttManager;

  private mqttClient: MqttClient | null = null;

  @Track public isConnected: boolean = false;
  @Track public latestMessage: string = '正在初始化...';
  @Track public isFallDetected: boolean = false; // 明确跟踪摔倒状态
  @Track public fallTimestamp: number = 0; // 摔倒时间戳
  @Track public fallRecords: FallRecord[] = []; // 摔倒记录列表
  
  @Track public isSedentaryDetected: boolean = false; // 久坐状态
  @Track public sedentaryTimestamp: number = 0; // 久坐时间戳
  @Track public sedentaryRecords: SedentaryRecord[] = []; // 久坐记录列表
  
  private fallRecoveryTimer: number = -1; // 摔倒自动恢复定时器
  private sedentaryRecoveryTimer: number = -1; // 久坐自动恢复定时器
  private readonly FALL_RECOVERY_DELAY: number = 3000; // 3秒后自动恢复
  private readonly SEDENTARY_RECOVERY_DELAY: number = 3000; // 3秒后自动恢复
  private lastRecordedFallTimestamp: number = 0; // 上次记录的摔倒时间戳，避免重复记录
  private lastRecordedSedentaryTimestamp: number = 0; // 上次记录的久坐时间戳

  private constructor() {
    this.initClient();
  }

  public static getInstance(): MqttManager {
    if (!MqttManager.instance) {
      MqttManager.instance = new MqttManager();
    }
    return MqttManager.instance;
  }

  private initClient() {
    // 修正 clientId 的模板字符串语法，确保 ID 有效且不冲突
    const clientId = `HarmonyOS_Client_sad`; // 添加随机数
    const clientOptions: MqttClientOptions = {
      url: BROKER_URL,
      // 缩短 clientId，避免超过 MQTT 协议的 23 字节限制（原 ID 过长导致初始化失败）
      clientId: clientId,
      persistenceType: 1,
    };

    try {
      this.mqttClient = MqttAsync.createMqtt(clientOptions);
      // 设置监听器
      this.setupListeners(this.mqttClient); // 移动到 try 块中
      console.log('[mqtt]:MQTT 客户端初始化成功asdf。');
      // 设置日志级别
      // this.mqttClient.setMqttTrace(6); // MQTTASYNC_TRACE_SEVERE  // 确保在 mqttClient 实例创建后再调用
    } catch (e) {
      console.error('[mqtt]:MQTT 客户端初始化失败:', e);
      this.latestMessage = `MQTT 初始化失败: ${(e as Error).message}`;
    }
  }

  private setupListeners(client: MqttClient) {
    client.connectLost((err: Error, data: MqttResponse) => {
      this.isConnected = false;
      console.error('[mqtt]:MQTT 连接丢失:', err, data);
      this.latestMessage = `连接丢失: ${data.message || '请检查网络或Broker状态'}`;
      // 清除定时器
      this.clearFallRecoveryTimer();
      // 尝试重新连接
      this.reconnect();
    });

    client.messageArrived((err: Error, data: MqttMessage) => {
      if (err) {
        console.error('[mqtt]:接收消息错误:', err);
        return;
      }
      console.log(`[mqtt]:💬 messageArrived 回调触发! topic=${data.topic}`);
      this.handleMessage(data.topic, data.payload);
    });
  }

  // 添加测试连接方法
  public async testConnection(): Promise<boolean> {
    try {
      if (!this.mqttClient) {
        console.log('[mqtt]:MQTT客户端未初始化');
        return false;
      }

      // 尝试建立短连接测试
      const connectOptions: MqttConnectOptions = {
        connectTimeout: 10,
        keepAliveInterval: 30,
        cleanSession: true,
        userName: "",
        password: "",
        MQTTVersion: 4, // 明确指定 MQTT 版本
      };

      const result = await this.mqttClient.connect(connectOptions);
      console.log('[mqtt]:连接测试结果:', result);

      if (result.code === 0) {
        // 测试成功后断开连接
        await this.mqttClient.disconnect();
        return true;
      }
      return false;
    } catch (error) {
      console.error('[mqtt]:连接测试失败:', error);
      return false;
    }
  }

  // 添加断开连接方法
  public async disconnect(): Promise<void> {
    if (this.mqttClient && this.isConnected) {
      try {
        await this.mqttClient.disconnect();
        this.isConnected = false;
        this.latestMessage = 'MQTT 连接已断开';
        // 清除定时器
        this.clearFallRecoveryTimer();
        console.log('[mqtt]:MQTT 连接已断开');
      } catch (error) {
        console.error('[mqtt]:断开连接失败:', error);
      }
    }
  }

  public async connectAndSubscribe(topic: string = ALERT_TOPIC) {
    if (!this.mqttClient) {
      this.initClient();
      console.log('[mqtt]:init成功退出');
      if (!this.mqttClient) {
        console.error('[mqtt]:MQTT 客户端初始化失败，无法连接和订阅。');
        this.latestMessage = 'MQTT 客户端初始化失败，请检查配置。';
        return;
      }
    }

    const connectOptions: MqttConnectOptions = {
      connectTimeout: 30,
      keepAliveInterval: 60,
      cleanSession: true,
      userName: "",
      password: "",
      MQTTVersion: 4, // 明确指定 MQTT 版本
      // 如果 Broker 使用 SSL/TLS，请配置 sslOptions
      // sslOptions: {
      //   enableServerCertAuth: true,
      //   trustStore: '/data/data/com.example.mysampleapp/files/ca.crt', // 替换为 CA 证书的实际路径
      // },
    };

    try {
      console.log('[mqtt]:正在尝试连接 MQTT Broker...');
      this.latestMessage = '正在连接 MQTT Broker...';

      // 使用 Promise 方式连接
      const connectResult = await this.mqttClient.connect(connectOptions);
      console.log('[mqtt]:MQTT 连接结果:', connectResult);
      this.isConnected = true;
      // 验证连接是否真正建立
      if (connectResult.code !== 0) {
        throw new Error(`连接失败，返回码: ${connectResult.code}, 消息: ${connectResult.message}`);
      }

      this.isConnected = true;
      console.log('[mqtt]:MQTT 连接成功。');

      const subscribeOptions: MqttSubscribeOptions = {
        topic: topic,
        qos: 1
      };

      const subscribeResult = await this.mqttClient.subscribe(subscribeOptions);
      console.log('[mqtt]:订阅结果:', subscribeResult);

      if (subscribeResult.code !== 0) {
        throw new Error(`订阅失败，返回码: ${subscribeResult.code}, 消息: ${subscribeResult.message}`);
      }

      console.log(`[mqtt]:✅ 成功订阅主题 ${topic}`);
      console.log(`[mqtt]:📡 等待接收消息...`);
      this.latestMessage = `✅ MQTT 已连接，等待主题 [${topic}] 消息...`;
      // 连接成功时，清除之前的摔倒状态和定时器
      this.clearFallRecoveryTimer();
      this.isFallDetected = false;
      this.fallTimestamp = 0;

    } catch (err) {
      this.isConnected = false;
      console.error('[mqtt]:MQTT 连接或订阅失败:', err);
      this.latestMessage = `连接/订阅失败: ${(err as Error).message || JSON.stringify(err)}, 堆栈: ${(err as Error).stack}`;
      console.log(`尝试连接到 URL: ${BROKER_URL}, 开发板(Broker) IP: ${BROKER_HOST}`);
      // 尝试重新连接
      this.reconnect();
    }
  }

  // 清除摔倒恢复定时器
  private clearFallRecoveryTimer(): void {
    if (this.fallRecoveryTimer !== -1) {
      clearTimeout(this.fallRecoveryTimer);
      this.fallRecoveryTimer = -1;
      console.log('[mqtt]:清除摔倒恢复定时器');
    }
  }

  // 启动摔倒自动恢复定时器
  private startFallRecoveryTimer(): void {
    // 先清除之前的定时器（如果存在）
    this.clearFallRecoveryTimer();
    
    console.log(`[mqtt]:启动摔倒自动恢复定时器，${this.FALL_RECOVERY_DELAY}ms 后自动恢复`);
    
    // 设置3秒后自动恢复
    this.fallRecoveryTimer = setTimeout(() => {
      console.log('[mqtt]:⏰ 定时器触发，自动恢复为正常状态');
      this.isFallDetected = false;
      this.fallTimestamp = 0;
      const currentTime: string = this.formatTimestamp(undefined);
      this.latestMessage = `✅ 已恢复正常状态 @ ${currentTime}`;
      this.fallRecoveryTimer = -1;
      console.log('[mqtt]:✅ 摔倒状态已自动清除');
    }, this.FALL_RECOVERY_DELAY)  as number;
  }

  // 清除久坐恢复定时器
  private clearSedentaryRecoveryTimer(): void {
    if (this.sedentaryRecoveryTimer !== -1) {
      clearTimeout(this.sedentaryRecoveryTimer);
      this.sedentaryRecoveryTimer = -1;
      console.log('[mqtt]:清除久坐恢复定时器');
    }
  }

  // 启动久坐自动恢复定时器
  private startSedentaryRecoveryTimer(): void {
    // 先清除之前的定时器（如果存在）
    this.clearSedentaryRecoveryTimer();
    
    console.log(`[mqtt]:启动久坐自动恢复定时器，${this.FALL_RECOVERY_DELAY}ms 后自动恢复`);
    
    // 设置3秒后自动恢复
    this.sedentaryRecoveryTimer = setTimeout(() => {
      console.log('[mqtt]:⏰ 定时器触发，久坐状态自动恢复为正常');
      this.isSedentaryDetected = false;
      this.sedentaryTimestamp = 0;
      const currentTime: string = this.formatTimestamp(undefined);
      this.latestMessage = `✅ 久坐已恢复正常 @ ${currentTime}`;
      this.sedentaryRecoveryTimer = -1;
      console.log('[mqtt]:✅ 久坐状态已自动清除');
    }, this.FALL_RECOVERY_DELAY)  as number;
  }

  // 清除摔倒状态
  private clearFallState(): void {
    if (this.isFallDetected) {
      console.log('[mqtt]:🔵 清除摔倒状态 (之前为true)');
    } else {
      console.log('[mqtt]:🔵 清除摔倒状态 (之前已是false)');
    }
    this.isFallDetected = false;
    this.fallTimestamp = 0;
    this.clearFallRecoveryTimer();
  }

  // 清除久坐状态
  private clearSedentaryState(): void {
    if (this.isSedentaryDetected) {
      console.log('[mqtt]:🟦 清除久坐状态 (之前为true)');
    } else {
      console.log('[mqtt]:🟦 清除久坐状态 (之前已是false)');
    }
    this.isSedentaryDetected = false;
    this.sedentaryTimestamp = 0;
    this.clearSedentaryRecoveryTimer();
  }

  // 格式化数字为两位数字符串（兼容性方法）
  private padZero(num: number): string {
    return num < 10 ? `0${num}` : `${num}`;
  }

  // 格式化时间戳为可读时间（使用本地时间）
  private formatTimestamp(timestamp: number | undefined): string {
    // 优先使用当前系统时间，确保时间准确
    const date = new Date();
    const year = date.getFullYear();
    const month = this.padZero(date.getMonth() + 1);
    const day = this.padZero(date.getDate());
    const hours = this.padZero(date.getHours());
    const minutes = this.padZero(date.getMinutes());
    const seconds = this.padZero(date.getSeconds());
    
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  }

  private handleMessage(topic: string, payload: string | ArrayBuffer) {
    console.log(`[mqtt]:📨📨📨 handleMessage 开始处理 topic=${topic}`);
    console.log(`[mqtt]:📨 payload类型=${typeof payload}`);
    let messageContent: string = '';

    if (typeof payload !== 'string') {
      try {
        const uint8Array: Uint8Array = new Uint8Array(payload as ArrayBuffer);
        let charCodes: number[] = [];
        for (let i = 0; i < uint8Array.length; i++) {
          charCodes.push(uint8Array[i]);
        }
        messageContent = String.fromCharCode(...charCodes);
      } catch (e) {
        messageContent = `收到原始数据，但解码失败: ${topic}`;
      }
    } else {
      messageContent = payload;
    }

    console.log(`[mqtt]:📩 收到原始消息 topic=${topic}, 内容长度=${messageContent.length}`);
    console.log(`[mqtt]:📩 消息内容: ${messageContent}`);

    try {
      const data = JSON.parse(messageContent) as AlertLike;
      console.log(`[mqtt]:✅ 解析JSON成功`);
      console.log(`[mqtt]:  - event=${data.event}`);
      console.log(`[mqtt]:  - alert_type=${data.alert_type}`);
      console.log(`[mqtt]:  - type=${data.type}`);
      
      const eventField = (data.event ?? data.alert_type ?? data.type ?? '') as string;
      const rawEvent: string = String(eventField).toLowerCase().trim();
      console.log(`[mqtt]:🔍 事件字段原始值="${eventField}"`);
      console.log(`[mqtt]:🔍 事件字段小写值="${rawEvent}"`);
      
      // 事件检测逻辑
      const isEmpty = rawEvent === '' || rawEvent === 'null' || rawEvent === 'none' || rawEvent === 'undefined';
      const hasFallKeyword = rawEvent.includes('fall') || rawEvent.includes('跌倒');
      const hasSedentaryKeyword = rawEvent.includes('sedentary') || rawEvent.includes('久坐') || rawEvent.includes('sitting_long');
      const hasNormalKeyword = rawEvent.includes('no fall') || rawEvent.includes('无跌倒') || 
                               rawEvent.includes('normal') || rawEvent.includes('正常') ||
                               rawEvent.includes('stand') || rawEvent.includes('站立') ||
                               rawEvent.includes('walk') || rawEvent.includes('行走');
      
      console.log(`[mqtt]:关键词检测 isEmpty=${isEmpty}, hasFall=${hasFallKeyword}, hasSedentary=${hasSedentaryKeyword}, hasNormal=${hasNormalKeyword}`);
      
      // 摔倒检测
      const isFall: boolean = !isEmpty && hasFallKeyword && !hasNormalKeyword && !hasSedentaryKeyword;
      // 久坐检测
      const isSedentary: boolean = !isEmpty && hasSedentaryKeyword && !hasNormalKeyword;
      
      console.log(`[mqtt]:事件检测结果 isFall=${isFall}, isSedentary=${isSedentary}`);

      if (isFall) {
        // 检测到摔倒
        const currentTimestamp = Date.now();
        const timeSinceLastRecord = currentTimestamp - this.lastRecordedFallTimestamp;
        
        console.log(`[mqtt]:🔴 检测到摔倒事件! 当前时间戳=${currentTimestamp}, 距上次记录=${timeSinceLastRecord}ms`);
        
        if (timeSinceLastRecord > 2000 || this.lastRecordedFallTimestamp === 0) {
          this.addFallRecord(currentTimestamp);
          this.lastRecordedFallTimestamp = currentTimestamp;
          console.log(`[mqtt]:✅ 新摔倒事件已记录! 总记录数=${this.fallRecords.length}`);
        }
        
        this.isFallDetected = true;
        this.fallTimestamp = currentTimestamp;
        this.clearSedentaryState(); // 清除久坐状态
        
        const fallTime: string = this.formatTimestamp(undefined);
        this.latestMessage = `🚨 严重告警: 检测到跌倒! @ ${fallTime}`;
        this.startFallRecoveryTimer();
      } else if (isSedentary) {
        // 检测到久坐
        const currentTimestamp = Date.now();
        const timeSinceLastRecord = currentTimestamp - this.lastRecordedSedentaryTimestamp;
        
        console.log(`[mqtt]:🟡🟡🟡 检测到久坐事件! 当前时间戳=${currentTimestamp}, 距上次记录=${timeSinceLastRecord}ms`);
        
        if (timeSinceLastRecord > 2000 || this.lastRecordedSedentaryTimestamp === 0) {
          console.log(`[mqtt]:📝 准备添加久坐记录...`);
          this.addSedentaryRecord(currentTimestamp);
          this.lastRecordedSedentaryTimestamp = currentTimestamp;
          console.log(`[mqtt]:✅ 新久坐事件已记录! 总记录数=${this.sedentaryRecords.length}`);
        } else {
          console.log(`[mqtt]:⚠️ 忽略重复久坐事件 (距上次 ${timeSinceLastRecord}ms)`);
        }
        
        console.log(`[mqtt]:设置 isSedentaryDetected=true, sedentaryTimestamp=${currentTimestamp}`);
        this.isSedentaryDetected = true;
        this.sedentaryTimestamp = currentTimestamp;
        this.clearFallState(); // 清除摔倒状态
        
        const sedentaryTime: string = this.formatTimestamp(undefined);
        this.latestMessage = `⚠️ 提醒: 检测到久坐! @ ${sedentaryTime}`;
        console.log(`[mqtt]:⚠️ 久坐消息已设置: ${this.latestMessage}`);
        console.log(`[mqtt]:启动久坐自动恢复定时器...`);
        this.startSedentaryRecoveryTimer();
        console.log(`[mqtt]:🟡 久坐处理完成，最终状态 isSedentaryDetected=${this.isSedentaryDetected}`);
      } else {
        // 正常状态
        console.log(`[mqtt]:🟢 设置为正常状态`);
        this.clearFallState();
        this.clearSedentaryState();
        
        const currentTime: string = this.formatTimestamp(undefined);
        if (eventField) {
          this.latestMessage = `✅ 正常状态: ${eventField} @ ${currentTime}`;
        } else {
          this.latestMessage = `✅ 正常状态 @ ${currentTime}`;
        }
      }
    } catch (e) {
      // JSON解析失败，使用纯文本匹配
      console.log(`[mqtt]:JSON解析失败，使用纯文本匹配, 错误=${(e as Error).message}`);
      const lower = messageContent.toLowerCase();
      const hasFallKeyword = lower.includes('fall') || messageContent.includes('跌倒');
      const hasSedentaryKeyword = lower.includes('sedentary') || messageContent.includes('久坐') || lower.includes('sitting_long');
      const hasNegativeKeyword = lower.includes('no fall') || lower.includes('无跌倒') || 
                                 lower.includes('normal') || lower.includes('正常') ||
                                 lower.includes('stand') || lower.includes('站立') ||
                                 lower.includes('walk') || lower.includes('行走');
      const isFall = hasFallKeyword && !hasNegativeKeyword && !hasSedentaryKeyword;
      const isSedentary = hasSedentaryKeyword && !hasNegativeKeyword;
      
      if (isFall) {
        // 检测到摔倒（纯文本匹配）
        const currentTimestamp = Date.now();
        const timeSinceLastRecord = currentTimestamp - this.lastRecordedFallTimestamp;
        
        console.log(`[mqtt]:🔴 纯文本匹配检测到摔倒! 时间戳=${currentTimestamp}, 距上次=${timeSinceLastRecord}ms`);
        
        // 添加摔倒记录
        if (timeSinceLastRecord > 2000 || this.lastRecordedFallTimestamp === 0) {
          console.log(`[mqtt]:📝 开始添加摔倒记录(纯文本)...`);
          this.addFallRecord(currentTimestamp);
          this.lastRecordedFallTimestamp = currentTimestamp;
          console.log(`[mqtt]:✅ 新摔倒事件已记录(纯文本)! 总记录数=${this.fallRecords.length}`);
        } else {
          console.log(`[mqtt]:⚠️ 忽略重复摔倒事件 ${timeSinceLastRecord}ms`);
        }
        
        this.isFallDetected = true;
        this.fallTimestamp = currentTimestamp;
        this.clearSedentaryState(); // 清除久坐状态
        
        const fallTime: string = this.formatTimestamp(undefined);
        this.latestMessage = `🚨 严重告警: 检测到跌倒! @ ${fallTime}`;
        console.error(`[mqtt]:🚨 摔倒状态已设置(纯文本)! 主题=${topic}, 时间=${fallTime}`);
        
        // 启动3秒自动恢复定时器
        this.startFallRecoveryTimer();
      } else if (isSedentary) {
        // 检测到久坐（纯文本匹配）
        const currentTimestamp = Date.now();
        const timeSinceLastRecord = currentTimestamp - this.lastRecordedSedentaryTimestamp;
        
        console.log(`[mqtt]:🟡 纯文本匹配检测到久坐! 时间戳=${currentTimestamp}, 距上次=${timeSinceLastRecord}ms`);
        
        // 添加久坐记录
        if (timeSinceLastRecord > 2000 || this.lastRecordedSedentaryTimestamp === 0) {
          console.log(`[mqtt]:📝 开始添加久坐记录(纯文本)...`);
          this.addSedentaryRecord(currentTimestamp);
          this.lastRecordedSedentaryTimestamp = currentTimestamp;
          console.log(`[mqtt]:✅ 新久坐事件已记录(纯文本)! 总记录数=${this.sedentaryRecords.length}`);
        } else {
          console.log(`[mqtt]:⚠️ 忽略重复久坐事件 ${timeSinceLastRecord}ms`);
        }
        
        this.isSedentaryDetected = true;
        this.sedentaryTimestamp = currentTimestamp;
        this.clearFallState(); // 清除摔倒状态
        
        const sedentaryTime: string = this.formatTimestamp(undefined);
        this.latestMessage = `⚠️ 提醒: 检测到久坐! @ ${sedentaryTime}`;
        console.log(`[mqtt]:⚠️ 久坐状态已设置(纯文本)! 主题=${topic}, 时间=${sedentaryTime}`);
        
        // 启动3秒自动恢复定时器
        this.startSedentaryRecoveryTimer();
      } else {
        // 正常消息（纯文本）
        console.log(`[mqtt]:🟢 纯文本匹配：清除所有状态`);
        this.clearFallState();
        this.clearSedentaryState();
        const currentTime: string = this.formatTimestamp(undefined);
        this.latestMessage = `✅ 正常状态: ${messageContent.substring(0, 50)} @ ${currentTime}`;
        console.log(`[mqtt]:✅ 收到正常消息(纯文本) 主题=${topic}, 所有状态已清除`);
      }
    }
    console.log(`[mqtt]:📊 最终状态 isFallDetected=${this.isFallDetected}, isSedentaryDetected=${this.isSedentaryDetected}, latestMessage=${this.latestMessage}`);
  }

  // 重新连接方法
  private async reconnect() {
    console.log('[mqtt]:尝试重新连接 MQTT...');
    this.latestMessage = '尝试重新连接 MQTT...';
    setTimeout(() => {
      this.connectAndSubscribe();
    }, 5000); // 5秒后重试
  }

  // 添加摔倒记录
  private addFallRecord(timestamp: number): void {
    console.log(`[mqtt]:📝 addFallRecord 被调用, timestamp=${timestamp}`);
    console.log(`[mqtt]:添加前 fallRecords.length=${this.fallRecords.length}`);
    
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth() + 1)}.${this.padZero(now.getDate())}`;
    
    const newRecord: FallRecord = {
      time: timeStr,
      date: dateStr,
      timestamp: timestamp
    };
    
    console.log(`[mqtt]:创建新记录: ${dateStr} ${timeStr}`);
    
    // 将新记录添加到数组开头（最新的在上面）
    // 使用数组解构创建新数组，触发响应式更新
    const oldLength = this.fallRecords.length;
    this.fallRecords = [newRecord, ...this.fallRecords];
    const newLength = this.fallRecords.length;
    
    console.log(`[mqtt]:✅ 摔倒记录已添加! ${dateStr} ${timeStr}`);
    console.log(`[mqtt]:数组长度变化: ${oldLength} -> ${newLength}`);
    console.log(`[mqtt]:当前所有记录(${this.fallRecords.length}条):`, JSON.stringify(this.fallRecords.map(r => `${r.date} ${r.time}`)));
  }

  // 添加久坐记录
  private addSedentaryRecord(timestamp: number): void {
    console.log(`[mqtt]:📝 addSedentaryRecord 被调用, timestamp=${timestamp}`);
    console.log(`[mqtt]:添加前 sedentaryRecords.length=${this.sedentaryRecords.length}`);
    
    const now = new Date(timestamp);
    const timeStr = `${this.padZero(now.getHours())}:${this.padZero(now.getMinutes())}:${this.padZero(now.getSeconds())}`;
    const dateStr = `${now.getFullYear()}.${this.padZero(now.getMonth() + 1)}.${this.padZero(now.getDate())}`;
    
    const newRecord: SedentaryRecord = {
      time: timeStr,
      date: dateStr,
      timestamp: timestamp
    };
    
    console.log(`[mqtt]:创建新久坐记录: ${dateStr} ${timeStr}`);
    
    // 将新记录添加到数组开头（最新的在上面）
    const oldLength = this.sedentaryRecords.length;
    this.sedentaryRecords = [newRecord, ...this.sedentaryRecords];
    const newLength = this.sedentaryRecords.length;
    
    console.log(`[mqtt]:✅ 久坐记录已添加! ${dateStr} ${timeStr}`);
    console.log(`[mqtt]:数组长度变化: ${oldLength} -> ${newLength}`);
    console.log(`[mqtt]:当前所有久坐记录(${this.sedentaryRecords.length}条):`, JSON.stringify(this.sedentaryRecords.map(r => `${r.date} ${r.time}`)));
  }

  // ========== 清理缓存功能 ==========
  /**
   * 清空所有摔倒记录
   */
  public clearFallRecords(): void {
    console.log(`[mqtt]:清理摔倒记录，当前记录数: ${this.fallRecords.length}`);
    this.fallRecords = [];
    this.lastRecordedFallTimestamp = 0;
    console.log('[mqtt]:✅ 摔倒记录已清空');
  }

  /**
   * 重置MQTT状态（不断开连接）
   */
  public resetMqttState(): void {
    console.log('[mqtt]:重置MQTT状态');
    this.isFallDetected = false;
    this.fallTimestamp = 0;
    this.isSedentaryDetected = false;
    this.sedentaryTimestamp = 0;
    this.latestMessage = '状态已重置';
    this.clearFallRecoveryTimer();
    this.clearSedentaryRecoveryTimer();
    console.log('[mqtt]:✅ MQTT状态已重置');
  }

  /**
   * 获取缓存统计信息
   */
  public getCacheStats(): CacheStats {
    const fallCount = this.fallRecords.length;
    const sedentaryCount = this.sedentaryRecords.length;
    
    const oldestFallRecord = fallCount > 0 ? 
      `${this.fallRecords[fallCount - 1].date} ${this.fallRecords[fallCount - 1].time}` : '无';
    const newestFallRecord = fallCount > 0 ? 
      `${this.fallRecords[0].date} ${this.fallRecords[0].time}` : '无';
      
    const oldestSedentaryRecord = sedentaryCount > 0 ? 
      `${this.sedentaryRecords[sedentaryCount - 1].date} ${this.sedentaryRecords[sedentaryCount - 1].time}` : '无';
    const newestSedentaryRecord = sedentaryCount > 0 ? 
      `${this.sedentaryRecords[0].date} ${this.sedentaryRecords[0].time}` : '无';
    
    const stats: CacheStats = {
      fallCount: fallCount,
      sedentaryCount: sedentaryCount,
      oldestFallRecord: oldestFallRecord,
      newestFallRecord: newestFallRecord,
      oldestSedentaryRecord: oldestSedentaryRecord,
      newestSedentaryRecord: newestSedentaryRecord
    };
    
    return stats;
  }

  /**
   * 清理所有缓存数据
   */
  public clearAllCache(): void {
    console.log('[mqtt]:🧹 开始清理所有缓存...');
    this.clearFallRecords();
    this.sedentaryRecords = []; // 清空久坐记录
    this.lastRecordedSedentaryTimestamp = 0;
    this.resetMqttState();
    console.log('[mqtt]:✅ 所有缓存已清理完成');
  }
}