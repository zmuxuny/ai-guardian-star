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
//昇腾开发板ip:192.168.137.100
// 【!!! 重要配置: 替换为您开发板的实际 IP 地址 (192.168.43.147) !!!】
// 这里的 IP 必须是 Broker 所在的开发板的 IP
const BROKER_HOST = '192.168.137.100';
const BROKER_PORT = 1883;
const BROKER_URL = `tcp://${BROKER_HOST}:${BROKER_PORT}`;  // 修改：使用 tcp:// 前缀，匹配 HarmonyOS MQTT 库要求
const ALERT_TOPIC = 'ai_guardian/alerts/#';

@Observed
export class MqttManager {
  private static instance: MqttManager;

  private mqttClient: MqttClient | null = null;

  public isConnected: boolean = false;
  public latestMessage: string = '正在初始化...';

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
      // 尝试重新连接
      this.reconnect();
    });

    client.messageArrived((err: Error, data: MqttMessage) => {
      if (err) {
        console.error('[mqtt]:接收消息错误:', err);
        return;
      }
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

      console.log(`成功订阅主题 ${topic}`);
      this.latestMessage = `✅ MQTT 已连接，等待主题 [${topic}] 消息...`;

    } catch (err) {
      this.isConnected = false;
      console.error('[mqtt]:MQTT 连接或订阅失败:', err);
      this.latestMessage = `连接/订阅失败: ${(err as Error).message || JSON.stringify(err)}, 堆栈: ${(err as Error).stack}`;
      console.log(`尝试连接到 URL: ${BROKER_URL}, 开发板(Broker) IP: ${BROKER_HOST}`);
      // 尝试重新连接
      this.reconnect();
    }
  }

  private handleMessage(topic: string, payload: string | ArrayBuffer) {
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

    try {
      const data = JSON.parse(messageContent) as AlertLike;
      const eventField = (data.event ?? data.alert_type ?? data.type ?? '') as string;
      const rawEvent: string = String(eventField).toLowerCase();
      const isFall: boolean = rawEvent.includes('fall') || rawEvent.includes('跌倒');
      const ts: number | undefined = data.timestamp;

      if (isFall) {
        const millis: number = ts !== undefined ? (ts > 1e12 ? ts : ts * 1000) : Date.now();
        const fallTime: string = new Date(millis).toLocaleTimeString('zh-CN');
        this.latestMessage = `🚨 严重告警: 检测到跌倒! @ ${fallTime}`;
        console.error(`[mqtt]:🚨 检测到摔倒事件! 主题=${topic}, 时间=${fallTime}, 原始数据=${messageContent}`);
      } else {
        this.latestMessage = `[${topic}] 消息: ${messageContent}`;
      }
    } catch (e) {
      // 纯文本关键字兜底
      const lower = messageContent.toLowerCase();
      if (lower.includes('fall') || messageContent.includes('跌倒')) {
        const fallTime: string = new Date().toLocaleTimeString('zh-CN');
        this.latestMessage = `🚨 严重告警: 检测到跌倒! @ ${fallTime}`;
        console.error(`[mqtt]:🚨 检测到摔倒事件(纯文本匹配)! 主题=${topic}, 时间=${fallTime}, 原始数据=${messageContent}`);
      } else {
        this.latestMessage = `[${topic}] 原始消息: ${messageContent}`;
      }
    }
    console.log(`[mqtt]:接收消息 topic=${topic}, 内容=${messageContent}`);
  }

  // 重新连接方法
  private async reconnect() {
    console.log('[mqtt]:尝试重新连接 MQTT...');
    this.latestMessage = '尝试重新连接 MQTT...';
    setTimeout(() => {
      this.connectAndSubscribe();
    }, 5000); // 5秒后重试
  }
}