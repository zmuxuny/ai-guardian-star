/**
 * DatabaseHelper.ets — 守护星 ArkDB 数据库核心模块
 *
 * 📦 数据库：GuardianStar.db（默认沙箱路径）
 * 📋 数据表：
 *   - t_user        用户账号信息（含密码哈希）
 *   - t_health_event 健康事件（摔倒 / 久坐）
 *   - t_video_record 监控视频元数据（路径 + 元信息，7天滚动覆盖）
 *
 * 🗂️ 当前版本：DB_VERSION = 1
 * ⚠️  升级数据库版本时，在 migrateDatabase() 追加 if (v === N) 分支即可
 */

import { relationalStore } from "@kit.ArkData";
import { BusinessError } from "@kit.BasicServicesKit";
import { hilog } from "@kit.PerformanceAnalysisKit";
import { Context } from "@kit.AbilityKit";

// ─── 日志 Tag ────────────────────────────────────────────────
const DOMAIN = 0x0001;
const TAG = "DatabaseHelper";

// ─── 数据库配置 ───────────────────────────────────────────────
const DB_NAME = "GuardianStar.db";
const DB_VERSION = 3; // v3: add nickname column to t_user

const STORE_CONFIG: relationalStore.StoreConfig = {
  name: DB_NAME,
  securityLevel: relationalStore.SecurityLevel.S2, // S2：含敏感个人信息，不加密但受系统保护
  encrypt: false,
  isReadOnly: false,
};

// ─── 建表 SQL ─────────────────────────────────────────────────

/** 用户账号表 */
const SQL_CREATE_USER = `CREATE TABLE IF NOT EXISTS t_user (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    nickname        TEXT,
    phone           TEXT,
    password_hash   TEXT    NOT NULL,
    avatar_path     TEXT,
    email           TEXT,
    address         TEXT,
    bind_elder_id   TEXT,
    create_time     INTEGER NOT NULL
  )`

/** 迁移：为旧版 t_user 补加 nickname 列（IF NOT EXISTS 不支持，用 try-catch 容错） */
const SQL_ADD_NICKNAME_COLUMN = `ALTER TABLE t_user ADD COLUMN nickname TEXT`;

/** 个人设置表 (云端/本地同步) */
const SQL_CREATE_SETTING = `CREATE TABLE IF NOT EXISTS t_setting (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    setting_key     TEXT    NOT NULL,
    setting_value   TEXT    NOT NULL,
    update_time     INTEGER NOT NULL,
    UNIQUE(username, setting_key)
  )`;

/** 健康事件表（摔倒 / 久坐） */
const SQL_CREATE_HEALTH_EVENT = `CREATE TABLE IF NOT EXISTS t_health_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT    NOT NULL,
    event_time      INTEGER NOT NULL,
    date_str        TEXT    NOT NULL,
    time_str        TEXT    NOT NULL,
    severity        INTEGER NOT NULL DEFAULT 1,
    is_handled      INTEGER NOT NULL DEFAULT 0,
    remark          TEXT,
    username        TEXT    NOT NULL DEFAULT ''
  )`;

/** 监控视频元数据表（7 天滚动覆盖，不存视频二进制） */
const SQL_CREATE_VIDEO_RECORD = `CREATE TABLE IF NOT EXISTS t_video_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT    NOT NULL,
    thumbnail_path  TEXT,
    duration_sec    INTEGER NOT NULL DEFAULT 0,
    file_size_kb    INTEGER NOT NULL DEFAULT 0,
    record_time     INTEGER NOT NULL,
    date_str        TEXT    NOT NULL,
    is_exported     INTEGER NOT NULL DEFAULT 0,
    username        TEXT    NOT NULL DEFAULT ''
  )`;

// ─── 数据接口定义 ─────────────────────────────────────────────

export interface UserInfo {
  id?: number;
  username: string;
  nickname?: string;
  phone?: string;
  passwordHash: string;
  avatarPath?: string;
  email?: string;
  address?: string;
  bindElderId?: string;
  createTime: number;
}

export interface UserSetting {
  id?: number;
  username: string;
  settingKey: string;
  settingValue: string;
  updateTime: number;
}

export interface HealthEvent {
  id?: number;
  /** 'fall' | 'sedentary' */
  eventType: string;
  eventTime: number;
  dateStr: string;
  timeStr: string;
  /** 严重程度 1-低 2-中 3-高 */
  severity: number;
  isHandled: number;
  remark?: string;
  username: string; // 归属用户，用于多账号隔离
}

export interface VideoRecord {
  id?: number;
  filePath: string;
  thumbnailPath?: string;
  durationSec: number;
  fileSizeKb: number;
  recordTime: number;
  dateStr: string;
  isExported: number;
}

// ─── DatabaseHelper 单例 ──────────────────────────────────────

// ─── 保留天数常量 ──────────────────────────────────────────────
/** 免费版最大保留天数 */
export const FREE_RETENTION_DAYS = 7;
/** 会员可选的保留天数列表 */
export const VIP_RETENTION_OPTIONS = [14, 30, 90];
/** 所有可选天数（展示给用户） */
export const ALL_RETENTION_OPTIONS = [7, 14, 30, 90];
/** AppStorage key：用户当前选择的保留天数 */
export const STORAGE_KEY_RETENTION = "retentionDays";

export class DatabaseHelper {
  private static instance: DatabaseHelper;
  private store: relationalStore.RdbStore | undefined = undefined;
  private initPromise: Promise<void> | undefined = undefined;

  private constructor() {}

  /** 获取当前保留天数（从 AppStorage 读，默认7天） */
  public getRetentionDays(): number {
    const v = AppStorage.get<number>(STORAGE_KEY_RETENTION);
    return v !== undefined && v > 0 ? v : FREE_RETENTION_DAYS;
  }

  /** 设置保留天数并存入 AppStorage（调用方负责会员校验） */
  public setRetentionDays(days: number): void {
    AppStorage.setOrCreate<number>(STORAGE_KEY_RETENTION, days);
    hilog.info(DOMAIN, TAG, `保留天数已设为 ${days} 天`);
  }

  public static getInstance(): DatabaseHelper {
    if (!DatabaseHelper.instance) {
      DatabaseHelper.instance = new DatabaseHelper();
    }
    return DatabaseHelper.instance;
  }

  // ── 初始化入口（幂等，可多次调用）──────────────────────────
  public async init(context: Context): Promise<void> {
    if (this.store !== undefined) return; // 已初始化，直接返回
    if (this.initPromise !== undefined) return this.initPromise; // 初始化进行中，等待

    this.initPromise = this._doInit(context);
    return this.initPromise;
  }

  private async _doInit(context: Context): Promise<void> {
    try {
      this.store = await relationalStore.getRdbStore(context, STORE_CONFIG);
      hilog.info(DOMAIN, TAG, "RdbStore 获取成功");
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `getRdbStore 失败 code=${err.code} msg=${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
    await this.migrateDatabase();
  }

  /** 【公开方法】获取 RdbStore 实例（用于诊断工具等高级操作） */
  public getRdbStore(): relationalStore.RdbStore {
    if (!this.store) {
      throw new Error("DatabaseHelper 未初始化，请先调用 init(context)");
    }
    return this.store;
  }

  // ── 数据库版本迁移 ────────────────────────────
  private async migrateDatabase(): Promise<void> {
    if (!this.store) return;

    // ArkDB 官方推荐使用 store.version 进行版本管理
    let currentVersion = this.store.version;
    hilog.info(DOMAIN, TAG, `数据库当前版本: ${currentVersion}`);

    // 直接无条件执行所有建表语句，利用 IF NOT EXISTS 保证安全。
    // 这能防范由于先前版本号或事务错误导致表未正常建立，却又升了版本号的死锁问题。
    try {
      await this.store.executeSql(SQL_CREATE_USER);
      await this.store.executeSql(SQL_CREATE_HEALTH_EVENT);
      await this.store.executeSql(SQL_CREATE_VIDEO_RECORD);
      await this.store.executeSql(SQL_CREATE_SETTING);
      hilog.info(DOMAIN, TAG, "所有数据表校验/创建完成");
    } catch (e) {
      hilog.error(DOMAIN, TAG, `执行建表语句失败: ${JSON.stringify(e)}`);
    }

    if (currentVersion < 2) {
      this.store.version = 2;
      hilog.info(DOMAIN, TAG, `数据库版本已更新为: 2`);
    }

    // v3：为已有 t_user 补加 nickname 列（新建表已含此列，旧库需 ALTER）
    if (currentVersion < 3) {
      try {
        await this.store.executeSql(SQL_ADD_NICKNAME_COLUMN);
        hilog.info(DOMAIN, TAG, "t_user.nickname 列添加成功");
      } catch (e) {
        // 列已存在时 SQLite 会报错，直接忽略即可
        hilog.warn(DOMAIN, TAG, "t_user.nickname 列可能已存在，跳过");
      }
      this.store.version = 3;
      hilog.info(DOMAIN, TAG, `数据库版本已更新为: 3`);
    }
  }

  // ── 安全获取 store（断言已初始化）─────────────────────────
  private getStore(): relationalStore.RdbStore {
    if (!this.store) throw new Error("DatabaseHelper 未初始化，请先调用 init(context)");
    return this.store;
  }

  // ════════════════════════════════════════════════════════════
  //  用户账号 CRUD
  // ════════════════════════════════════════════════════════════

  /** 新增用户，返回 rowId */
  public async insertUser(user: UserInfo): Promise<number> {
    const values: relationalStore.ValuesBucket = {
      username: user.username,
      nickname: user.nickname ?? null,
      phone: user.phone ?? null,
      password_hash: user.passwordHash,
      avatar_path: user.avatarPath ?? null,
      email: user.email ?? null,
      address: user.address ?? null,
      bind_elder_id: user.bindElderId ?? null,
      create_time: user.createTime,
    };
    try {
      const rowId = await this.getStore().insert("t_user", values);
      hilog.info(DOMAIN, TAG, `insertUser 成功 rowId=${rowId}`);
      return rowId;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `insertUser 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 按手机号查询用户（用于登录验证） */
  public async queryUserByPhone(phone: string): Promise<UserInfo | null> {
    const predicates = new relationalStore.RdbPredicates("t_user");
    predicates.equalTo("phone", phone);
    return this._querySingleUser(predicates);
  }

  /** 按用户名查询用户 */
  public async queryUserByUsername(username: string): Promise<UserInfo | null> {
    const predicates = new relationalStore.RdbPredicates("t_user");
    predicates.equalTo("username", username);
    return this._querySingleUser(predicates);
  }

  /** 内部：按谓词查单条用户并映射为 UserInfo */
  private async _querySingleUser(
    predicates: relationalStore.RdbPredicates,
  ): Promise<UserInfo | null> {
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().query(predicates, [
        "id",
        "username",
        "nickname",
        "phone",
        "password_hash",
        "avatar_path",
        "email",
        "address",
        "bind_elder_id",
        "create_time",
      ]);
      if (resultSet.goToNextRow()) {
        const user: UserInfo = {
          id: resultSet.getLong(resultSet.getColumnIndex("id")),
          username: resultSet.getString(resultSet.getColumnIndex("username")),
          nickname: resultSet.getString(resultSet.getColumnIndex("nickname")),
          phone: resultSet.getString(resultSet.getColumnIndex("phone")),
          passwordHash: resultSet.getString(resultSet.getColumnIndex("password_hash")),
          avatarPath: resultSet.getString(resultSet.getColumnIndex("avatar_path")),
          email: resultSet.getString(resultSet.getColumnIndex("email")),
          address: resultSet.getString(resultSet.getColumnIndex("address")),
          bindElderId: resultSet.getString(resultSet.getColumnIndex("bind_elder_id")),
          createTime: resultSet.getLong(resultSet.getColumnIndex("create_time")),
        };
        return user;
      }
      return null;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `_querySingleUser 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    } finally {
      resultSet?.close(); // ⚠️ 必须关闭 ResultSet，释放内存
    }
  }

  /** 更新用户信息（头像、昵称、地址等），按 id 定位 */
  public async updateUser(user: UserInfo): Promise<number> {
    if (user.id === undefined) throw new Error("updateUser: id 不能为空");
    const values: relationalStore.ValuesBucket = {
      username: user.username,
      nickname: user.nickname ?? null,
      phone: user.phone ?? null,
      avatar_path: user.avatarPath ?? null,
      email: user.email ?? null,
      address: user.address ?? null,
    };
    const predicates = new relationalStore.RdbPredicates("t_user");
    predicates.equalTo("id", user.id);
    try {
      const rows = await this.getStore().update(values, predicates);
      hilog.info(DOMAIN, TAG, `updateUser 成功，影响行数=${rows}`);
      return rows;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `updateUser 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 单独更新用户昵称（按 username 定位） */
  public async updateNickname(username: string, nickname: string): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_user");
    predicates.equalTo("username", username);
    try {
      await this.getStore().update({ nickname: nickname }, predicates);
      hilog.info(DOMAIN, TAG, `updateNickname 成功 username=${username}`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `updateNickname 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 更新密码哈希 */
  public async updatePasswordHash(userId: number, newHash: string): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_user");
    predicates.equalTo("id", userId);
    try {
      await this.getStore().update({ password_hash: newHash }, predicates);
      hilog.info(DOMAIN, TAG, `updatePasswordHash 成功 userId=${userId}`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `updatePasswordHash 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  // ════════════════════════════════════════════════════════════
  //  个人设置 CRUD（云端 / 本地缓存）
  // ════════════════════════════════════════════════════════════

  /** 保存或更新用户的指定设置 */
  public async saveSetting(username: string, key: string, value: string): Promise<void> {
    const values: relationalStore.ValuesBucket = {
      username: username,
      setting_key: key,
      setting_value: value,
      update_time: Date.now(),
    };
    try {
      // 冲突替换（由于在建表时指定 UNIQUE(username, setting_key)）
      // HarmonyOS SQLite 默认的 insert 时若有 UNIQUE 约束可能报错，这里可用 update or insert 的变通。
      const predicates = new relationalStore.RdbPredicates("t_setting");
      predicates.equalTo("username", username).and().equalTo("setting_key", key);
      const resultSet = await this.getStore().query(predicates, ["id"]);
      const hasExist = resultSet.goToNextRow();
      resultSet.close();

      if (hasExist) {
        await this.getStore().update(values, predicates);
      } else {
        await this.getStore().insert("t_setting", values);
      }
      hilog.info(DOMAIN, TAG, `saveSetting 成功: user=${username} key=${key} value=${value}`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `saveSetting 失败: ${err.message}`);
    }
  }

  /** 加载用户的指定设置 */
  public async loadSetting(username: string, key: string): Promise<string | null> {
    const predicates = new relationalStore.RdbPredicates("t_setting");
    predicates.equalTo("username", username).and().equalTo("setting_key", key);
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().query(predicates, ["setting_value"]);
      if (resultSet.goToNextRow()) {
        return resultSet.getString(resultSet.getColumnIndex("setting_value"));
      }
      return null;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `loadSetting 失败: ${err.message}`);
      return null;
    } finally {
      if (resultSet !== undefined) {
        resultSet.close();
      }
    }
  }

  // ════════════════════════════════════════════════════════════
  //  健康事件 CRUD（摔倒 / 久坐）
  // ════════════════════════════════════════════════════════════

  /** 插入健康事件，写入前自动滚动清理超出保留天数的旧记录，返回 rowId */
  public async insertHealthEvent(event: HealthEvent): Promise<number> {
    // 🔄 滚动清理：删除早于 retentionDays 天前的旧事件
    const cutoff = event.eventTime - this.getRetentionDays() * 24 * 60 * 60 * 1000;
    const oldPred = new relationalStore.RdbPredicates("t_health_event");
    oldPred.lessThan("event_time", cutoff);
    try {
      const deleted = await this.getStore().delete(oldPred);
      if (deleted > 0)
        hilog.info(
          DOMAIN,
          TAG,
          `滚动清理健康事件 ${deleted} 条（保留${this.getRetentionDays()}天）`,
        );
    } catch (_) {}

    // 确保 username 不为空字符串，使用默认值
    const effectiveUsername =
      event.username && event.username.trim() !== "" ? event.username : "default_user";

    const values: relationalStore.ValuesBucket = {
      event_type: event.eventType,
      event_time: event.eventTime,
      date_str: event.dateStr,
      time_str: event.timeStr,
      severity: event.severity,
      is_handled: event.isHandled,
      remark: event.remark ?? null,
      username: effectiveUsername,
    };
    try {
      const rowId = await this.getStore().insert("t_health_event", values);
      hilog.info(
        DOMAIN,
        TAG,
        `insertHealthEvent 成功 type=${event.eventType} rowId=${rowId} user=${effectiveUsername}`,
      );
      return rowId;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `insertHealthEvent 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 查询健康事件列表，只返回保留天数内、指定用户的记录，可按类型过滤，按时间倒序 */
  public async queryHealthEvents(eventType?: string, username?: string): Promise<HealthEvent[]> {
    const cutoff = Date.now() - this.getRetentionDays() * 24 * 60 * 60 * 1000;
    const predicates = new relationalStore.RdbPredicates("t_health_event");
    predicates.greaterThanOrEqualTo("event_time", cutoff);

    // 用户隔离：如果传入 username 且非空，查该用户的数据；否则查所有数据（兼容旧数据）
    if (username && username.trim() !== "") {
      predicates.equalTo("username", username);
      hilog.info(DOMAIN, TAG, `查询用户数据：${username}`);
    } else {
      // 不传或传空字符串时，不设置 username 过滤，查所有数据
      // 这样可以兼容未登录状态写入的记录（username=''）
      hilog.info(DOMAIN, TAG, `查询所有用户数据（username 为空）`);
    }

    if (eventType) predicates.equalTo("event_type", eventType);
    predicates.orderByDesc("event_time");
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().query(predicates, [
        "id",
        "event_type",
        "event_time",
        "date_str",
        "time_str",
        "severity",
        "is_handled",
        "remark",
        "username",
      ]);
      const list: HealthEvent[] = [];
      while (resultSet.goToNextRow()) {
        list.push({
          id: resultSet.getLong(resultSet.getColumnIndex("id")),
          eventType: resultSet.getString(resultSet.getColumnIndex("event_type")),
          eventTime: resultSet.getLong(resultSet.getColumnIndex("event_time")),
          dateStr: resultSet.getString(resultSet.getColumnIndex("date_str")),
          timeStr: resultSet.getString(resultSet.getColumnIndex("time_str")),
          severity: resultSet.getLong(resultSet.getColumnIndex("severity")),
          isHandled: resultSet.getLong(resultSet.getColumnIndex("is_handled")),
          remark: resultSet.getString(resultSet.getColumnIndex("remark")),
          username: resultSet.getString(resultSet.getColumnIndex("username")),
        });
      }
      hilog.info(
        DOMAIN,
        TAG,
        `queryHealthEvents 返回 ${list.length} 条，type=${eventType ?? "all"}, user=${username ?? "any"}`,
      );
      return list;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `queryHealthEvents 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    } finally {
      resultSet?.close();
    }
  }

  /** 标记事件为已处理 */
  public async markEventHandled(eventId: number): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_health_event");
    predicates.equalTo("id", eventId);
    try {
      await this.getStore().update({ is_handled: 1 }, predicates);
      hilog.info(DOMAIN, TAG, `markEventHandled 成功 id=${eventId}`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `markEventHandled 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 删除全部健康事件（清理缓存） */
  public async clearAllHealthEvents(): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_health_event");
    predicates.notEqualTo("id", -1); // 匹配全部行
    try {
      const rows = await this.getStore().delete(predicates);
      hilog.info(DOMAIN, TAG, `clearAllHealthEvents 删除 ${rows} 条`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `clearAllHealthEvents 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 【诊断方法】查询所有健康事件（不带任何过滤，用于调试） */
  public async queryAllHealthEventsForDebug(): Promise<HealthEvent[]> {
    const predicates = new relationalStore.RdbPredicates("t_health_event");
    predicates.orderByDesc("event_time");
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().query(predicates, [
        "id",
        "event_type",
        "event_time",
        "date_str",
        "time_str",
        "severity",
        "is_handled",
        "remark",
        "username",
      ]);
      const list: HealthEvent[] = [];
      while (resultSet.goToNextRow()) {
        list.push({
          id: resultSet.getLong(resultSet.getColumnIndex("id")),
          eventType: resultSet.getString(resultSet.getColumnIndex("event_type")),
          eventTime: resultSet.getLong(resultSet.getColumnIndex("event_time")),
          dateStr: resultSet.getString(resultSet.getColumnIndex("date_str")),
          timeStr: resultSet.getString(resultSet.getColumnIndex("time_str")),
          severity: resultSet.getLong(resultSet.getColumnIndex("severity")),
          isHandled: resultSet.getLong(resultSet.getColumnIndex("is_handled")),
          remark: resultSet.getString(resultSet.getColumnIndex("remark")),
          username: resultSet.getString(resultSet.getColumnIndex("username")),
        });
      }
      hilog.info(DOMAIN, TAG, `queryAllHealthEventsForDebug 返回 ${list.length} 条`);
      return list;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `queryAllHealthEventsForDebug 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    } finally {
      resultSet?.close();
    }
  }

  // ════════════════════════════════════════════════════════════
  //  监控视频 CRUD（7 天滚动覆盖策略）
  // ════════════════════════════════════════════════════════════

  /**
   * 插入视频元数据记录，并自动执行 7 天滚动清理：
   * - 先删除 7 天前（604800000ms）的旧记录
   * - 若剩余空间仍不足（超过 MAX_VIDEO_DAYS 天范围），继续压缩到 MIN_VIDEO_DAYS 天
   */
  public async insertVideoRecord(video: VideoRecord): Promise<number> {
    const retDays = this.getRetentionDays();
    const MIN_DAYS = Math.min(3, retDays); // 空间不足保底不超过保留天数
    const msPerDay = 24 * 60 * 60 * 1000;
    const now = video.recordTime;

    // Step 1：删除超过 retentionDays 的旧记录（真正滚动覆盖）
    await this._deleteVideosBefore(now - retDays * msPerDay);

    // Step 2：若记录数超 500 条，进一步压缩
    const count = await this._countVideoRecords();
    if (count > 500) {
      hilog.warn(DOMAIN, TAG, `视频记录数(${count})过多，压缩到 ${MIN_DAYS} 天`);
      await this._deleteVideosBefore(now - MIN_DAYS * msPerDay);
    }

    // Step 3：插入新记录
    const values: relationalStore.ValuesBucket = {
      file_path: video.filePath,
      thumbnail_path: video.thumbnailPath ?? null,
      duration_sec: video.durationSec,
      file_size_kb: video.fileSizeKb,
      record_time: video.recordTime,
      date_str: video.dateStr,
      is_exported: video.isExported,
    };
    try {
      const rowId = await this.getStore().insert("t_video_record", values);
      hilog.info(DOMAIN, TAG, `insertVideoRecord 成功 rowId=${rowId} path=${video.filePath}`);
      return rowId;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `insertVideoRecord 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 内部：删除 recordTime 早于 beforeTs 的视频记录（返回删除条数） */
  private async _deleteVideosBefore(beforeTs: number): Promise<number> {
    const predicates = new relationalStore.RdbPredicates("t_video_record");
    predicates.lessThan("record_time", beforeTs);
    try {
      const rows = await this.getStore().delete(predicates);
      if (rows > 0) hilog.info(DOMAIN, TAG, `滚动清理视频记录 ${rows} 条（早于 ${beforeTs}）`);
      return rows;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `_deleteVideosBefore 失败 ${err.code} ${err.message}`);
      return 0;
    }
  }

  /** 内部：统计视频记录总数 */
  private async _countVideoRecords(): Promise<number> {
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().querySql("SELECT COUNT(*) AS cnt FROM t_video_record");
      if (resultSet.goToNextRow()) {
        return resultSet.getLong(resultSet.getColumnIndex("cnt"));
      }
      return 0;
    } catch (e) {
      return 0;
    } finally {
      resultSet?.close();
    }
  }

  /** 查询视频列表，只返回保留天数内的记录，按录制时间倒序 */
  public async queryVideoRecords(limitDays?: number): Promise<VideoRecord[]> {
    const days = limitDays ?? this.getRetentionDays();
    const beforeTs = Date.now() - days * 24 * 60 * 60 * 1000;
    const predicates = new relationalStore.RdbPredicates("t_video_record");
    predicates.greaterThanOrEqualTo("record_time", beforeTs);
    predicates.orderByDesc("record_time");
    let resultSet: relationalStore.ResultSet | undefined;
    try {
      resultSet = await this.getStore().query(predicates, [
        "id",
        "file_path",
        "thumbnail_path",
        "duration_sec",
        "file_size_kb",
        "record_time",
        "date_str",
        "is_exported",
      ]);
      const list: VideoRecord[] = [];
      while (resultSet.goToNextRow()) {
        list.push({
          id: resultSet.getLong(resultSet.getColumnIndex("id")),
          filePath: resultSet.getString(resultSet.getColumnIndex("file_path")),
          thumbnailPath: resultSet.getString(resultSet.getColumnIndex("thumbnail_path")),
          durationSec: resultSet.getLong(resultSet.getColumnIndex("duration_sec")),
          fileSizeKb: resultSet.getLong(resultSet.getColumnIndex("file_size_kb")),
          recordTime: resultSet.getLong(resultSet.getColumnIndex("record_time")),
          dateStr: resultSet.getString(resultSet.getColumnIndex("date_str")),
          isExported: resultSet.getLong(resultSet.getColumnIndex("is_exported")),
        });
      }
      hilog.info(DOMAIN, TAG, `queryVideoRecords 返回 ${list.length} 条`);
      return list;
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `queryVideoRecords 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    } finally {
      resultSet?.close();
    }
  }

  /** 标记视频为已导出 */
  public async markVideoExported(videoId: number): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_video_record");
    predicates.equalTo("id", videoId);
    try {
      await this.getStore().update({ is_exported: 1 }, predicates);
      hilog.info(DOMAIN, TAG, `markVideoExported id=${videoId}`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `markVideoExported 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 手动强制清理所有视频元数据（仅清数据库记录，物理文件需调用方自行删除） */
  public async clearAllVideoRecords(): Promise<void> {
    const predicates = new relationalStore.RdbPredicates("t_video_record");
    predicates.notEqualTo("id", -1);
    try {
      const rows = await this.getStore().delete(predicates);
      hilog.info(DOMAIN, TAG, `clearAllVideoRecords 删除 ${rows} 条`);
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `clearAllVideoRecords 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  // ════════════════════════════════════════════════════════════
  //  数据库维护
  // ════════════════════════════════════════════════════════════

  /** 手动备份数据库到同沙箱路径下的 GuardianStar_backup.db */
  public async backup(): Promise<void> {
    try {
      await (this.getStore() as relationalStore.RdbStore).backup("GuardianStar_backup.db");
      hilog.info(DOMAIN, TAG, "数据库备份成功");
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `backup 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 从备份文件恢复数据库 */
  public async restore(): Promise<void> {
    try {
      await (this.getStore() as relationalStore.RdbStore).restore("GuardianStar_backup.db");
      hilog.info(DOMAIN, TAG, "数据库恢复成功");
    } catch (e) {
      const err = e as BusinessError;
      hilog.error(DOMAIN, TAG, `restore 失败 ${err.code} ${err.message}`);
      throw new Error(err.code + ": " + err.message);
    }
  }

  /** 彻底关闭 RdbStore（应用退出时调用） */
  public close(): void {
    if (this.store) {
      this.store.close();
      this.store = undefined;
      this.initPromise = undefined;
      hilog.info(DOMAIN, TAG, "RdbStore 已关闭");
    }
  }
}
