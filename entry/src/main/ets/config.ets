/**
 * config.ets — 全局配置常量
 * 所有服务器地址、端口、超时等集中管理，避免散落各处
 */

// ── ECS 云端服务器 ──────────────────────────────────────────
export const ECS_HOST = "117.78.9.144";
export const ECS_API_PORT = 8899;
export const ECS_VIDEO_PORT = 6001;
export const ECS_MQTT_PORT = 8883;
export const ECS_WS_PORT = 6000;

// ── 局域网开发板 ────────────────────────────────────────────
export const LAN_HOST = "192.168.137.100";
export const LAN_UPLOAD_PORT = 8080;

// ── 派生 URL ───────────────────────────────────────────────
export const ECS_BASE_URL = "https://api.aistar.asia";
export const VIDEO_FEED_URL = `http://${ECS_HOST}:${ECS_VIDEO_PORT}/video_feed`;
export const HEALTH_CHECK_URL = `http://${ECS_HOST}:${ECS_VIDEO_PORT}/api/stats`;
export const BROKER_URL = `ssl://${ECS_HOST}:${ECS_MQTT_PORT}`;
export const WS_INTERCOM_URL = `ws://${ECS_HOST}:${ECS_WS_PORT}/ws/intercom`;
export const BOARD_UPLOAD_URL = `http://${LAN_HOST}:${LAN_UPLOAD_PORT}/upload`;
export const BOARD_FACE_ENROLL_URL = `http://${LAN_HOST}:${LAN_UPLOAD_PORT}/api/face/enroll`;
export const BOARD_FACE_LIST_URL = `http://${LAN_HOST}:${LAN_UPLOAD_PORT}/api/face/list`;
export const BOARD_FACE_DELETE_URL = `http://${LAN_HOST}:${LAN_UPLOAD_PORT}/api/face`;

// ── MQTT ────────────────────────────────────────────────────
export const ALERT_TOPIC = "ai_guardian/alerts/#";
export const MQTT_CLIENT_ID = "HarmonyOS_Client_sad";
// 禁止在安装包内固化共享 broker 密码；后续由设备注册服务下发短期凭据并写入 Keystore。
export const MQTT_USERNAME = "harmony_app";
export const MQTT_PASSWORD = "";
// GuardianCA 自签名根证书（公钥，非私钥，可安全内嵌）
// 用于验证 broker TLS 证书，避免中间人攻击
export const MQTT_CA_CERT = `-----BEGIN CERTIFICATE-----
MIIDCzCCAfOgAwIBAgIUI2ewU09ORXFKFMmX8Ib5LhcHQG8wDQYJKoZIhvcNAQEL
BQAwFTETMBEGA1UEAwwKR3VhcmRpYW5DQTAeFw0yNjA2MDMwNjQyMDBaFw0zNjA1
MzEwNjQyMDBaMBUxEzARBgNVBAMMCkd1YXJkaWFuQ0EwggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQC9mWcF0t/xe8yhKqmuH37qEIMiB9X2Gp+CsaZQneHp
OUZHj5MAuKaTH2W4o4duD3SZHH7FH4PTq5AZ2HxhxrAC6g90qPy8zzpSaERtzu6B
HhwJ4QSlqsrUxAwe7vCahk+XgpY0cfzgaHooUelIqLvhwuTtLxv4YjkUJFVN2cT1
NoeuEAIUsB4cG35LUfhdfoJTwjyIvviG+vCkLXm2plpKnXEP1iqQaIOWNaq8oxh0
s1PBT4nsZNpG51FPkoCAzY8PE7KH0s3jNaXTpm260ThubV7PqIh4OCdagCVahCuG
yZNF7IlGuXQohBLt3LQk7HnwIpy26r8kVh5oOb61kEOVAgMBAAGjUzBRMB0GA1Ud
DgQWBBTAO3phEUVIvGnYOJHLkud7w1kSaDAfBgNVHSMEGDAWgBTAO3phEUVIvGnY
OJHLkud7w1kSaDAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQBx
T1fKwVUYfJfGQ++08Iih+LMFouH4u2ZmMM2o9eCFGToLwVStbs7fJ9sbh1Ka+VBd
UXW09I+hHqO75rff/yXwNEnO4sjKEjDNnir5ptASXhvrIgrhcwtW1I/A8CcwWXzU
5ydWUZ+UcFkGfdhJqxvMqbzwdVb8CIFTujRC8gsUPwDkw22dYnkw0zszwgPqi8Rf
Y3PAGI7MLs9SgGXxyXiIs28wu4uZA1wcwTbLqpSOhVCrcf0paPyoC7zgb+RTNkUa
JJvoFskofPpQ4JkQqdobQ06rE7JuFsuUB4prJ+9bl9HsI7P700SPtNYjNggTlE32
Kz6LI4sfTgmSL0/Otmzc
-----END CERTIFICATE-----`;

// ── AppStorage Keys ──────────────────────────────────────────
export const STORE_KEY_LOGGED_IN_USER = "loggedInUsername";
export const STORE_KEY_NICKNAME = "loggedInNickname";
export const STORE_KEY_AVATAR = "loggedInAvatarPath";
export const STORE_KEY_PHONE = "loggedInPhone";
export const STORE_KEY_EMAIL = "loggedInEmail";
export const STORE_KEY_RETENTION = "retentionDays";
export const STORE_KEY_AI_ENABLED = "aiAssistantEnabled";
export const STORE_KEY_AI_ACCESS_LEVEL = "aiAccessLevel";

// ── Preferences ──────────────────────────────────────────────
export const PREF_NAME_AUTH = "guardian_auth";
export const PREF_KEY_LAST_USERNAME = "lastUsername";
export const PREF_KEY_LAST_NICKNAME = "lastNickname";
export const PREF_KEY_PRIVACY_ACCEPTED = 'privacyAccepted';
export const PRIVACY_POLICY_URL = 'https://aistar.asia/legal/privacy/';
