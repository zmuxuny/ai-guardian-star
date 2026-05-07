/**
 * config.ets — 全局配置常量
 * 所有服务器地址、端口、超时等集中管理，避免散落各处
 */

// ── ECS 云端服务器 ──────────────────────────────────────────
export const ECS_HOST = '117.78.9.144';
export const ECS_API_PORT = 8899;
export const ECS_VIDEO_PORT = 6001;
export const ECS_MQTT_PORT = 1883;
export const ECS_WS_PORT = 6000;

// ── 局域网开发板 ────────────────────────────────────────────
export const LAN_HOST = '192.168.137.100';
export const LAN_UPLOAD_PORT = 8080;

// ── 派生 URL ───────────────────────────────────────────────
export const ECS_BASE_URL = `http://${ECS_HOST}:${ECS_API_PORT}`;
export const VIDEO_FEED_URL = `http://${ECS_HOST}:${ECS_VIDEO_PORT}/video_feed`;
export const HEALTH_CHECK_URL = `http://${ECS_HOST}:${ECS_VIDEO_PORT}/api/stats`;
export const BROKER_URL = `tcp://${ECS_HOST}:${ECS_MQTT_PORT}`;
export const WS_INTERCOM_URL = `ws://${ECS_HOST}:${ECS_WS_PORT}/ws/intercom`;
export const BOARD_UPLOAD_URL = `http://${LAN_HOST}:${LAN_UPLOAD_PORT}/upload`;

// ── MQTT ────────────────────────────────────────────────────
export const ALERT_TOPIC = 'ai_guardian/alerts/#';
export const MQTT_CLIENT_ID = 'HarmonyOS_Client_sad';

// ── AppStorage Keys ──────────────────────────────────────────
export const STORE_KEY_LOGGED_IN_USER = 'loggedInUsername';
export const STORE_KEY_NICKNAME = 'loggedInNickname';
export const STORE_KEY_AVATAR = 'loggedInAvatarPath';
export const STORE_KEY_PHONE = 'loggedInPhone';
export const STORE_KEY_EMAIL = 'loggedInEmail';
export const STORE_KEY_RETENTION = 'retentionDays';

// ── Preferences ──────────────────────────────────────────────
export const PREF_NAME_AUTH = 'guardian_auth';
export const PREF_KEY_LAST_USERNAME = 'lastUsername';
export const PREF_KEY_LAST_NICKNAME = 'lastNickname';
