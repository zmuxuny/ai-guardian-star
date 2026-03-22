# 守护星 ArkDB 数据库部署过程文档

**部署日期：** 2026-03-21
**目标项目：** `E:\caringSystem`
**操作者：** 简沅晞（ AI 辅助部署）
**参考文档：** 华为官方《通过关系型数据库实现数据持久化 (ArkTS)》

---

## 一、部署目标

在守护星 HarmonyOS APP（Stage 模型，ArkTS）中，基于 `@kit.ArkData` 的 `relationalStore` 模块，
建立一套本地关系型数据库（SQLite 底层），实现以下三类数据的持久化：

| 表名             | 用途                                                        |
| ---------------- | ----------------------------------------------------------- |
| `t_user`         | 用户账号信息（昵称、手机、密码哈希、头像、邮箱、地址等）    |
| `t_health_event` | 健康事件（摔倒 / 久坐），含时间、严重程度、是否已处理       |
| `t_video_record` | 监控视频元数据（文件路径、时长、大小、缩略图），7天滚动覆盖 |

---

## 二、新增文件

### `entry/src/main/ets/database/DatabaseHelper.ets`（新建，556 行）

**职责：** 数据库单例封装，提供所有表的增删改查接口。

**关键设计决策：**

1. **单例 + 幂等 init**
   使用 `getInstance()` 单例，`init(context)` 支持多次安全调用（通过 `initPromise` 防并发重入）。

2. **数据库配置**
   ```
   name: 'GuardianStar.db'
   securityLevel: S2（含个人信息，受系统保护，不加密以保证性能）
   路径：默认沙箱（应用卸载后自动清除）
   ```

3. **版本迁移（事务原子保护）**
   在 `migrateDatabase()` 中用 `createTransaction + PRAGMA user_version` 管理版本。
   当前 v0 → v1 建立全部三张表。后续升级只需追加 `if (version === N)` 分支。

4. **t_user 表字段：**
   id, username, phone, password_hash, avatar_path, email, address, bind_elder_id, create_time

5. **t_health_event 表字段：**
   id, event_type ('fall'|'sedentary'), event_time(ms时间戳), date_str, time_str, severity(1-3), is_handled, remark

6. **t_video_record 表字段：**
   id, file_path, thumbnail_path, duration_sec, file_size_kb, record_time(ms), date_str, is_exported

7. **视频 7 天滚动覆盖逻辑（`insertVideoRecord` 方法）：**
   - 每次插入前，先删除 7 天前的旧记录（`_deleteVideosBefore`）
   - 若视频元数据条数超过 500 条，自动压缩到 3 天（空间不足保底策略）
   - 注意：此方法只管数据库记录，物理视频文件需由调用方自行删除

8. **ResultSet 及时关闭**
   所有查询操作均在 `finally` 块中调用 `resultSet?.close()`，防止内存泄漏。

9. **备份 / 恢复**
   `backup()` → `GuardianStar_backup.db`（同沙箱路径）
   `restore()` ← `GuardianStar_backup.db`

---

## 三、修改文件

### 3.1 `entry/src/main/ets/entryability/EntryAbility.ets`（修改，80 行）

**修改内容：**

**新增 import：**
```typescript
import { DatabaseHelper } from '../database/DatabaseHelper';
```

**`onCreate` 末尾新增数据库初始化：**
```typescript
DatabaseHelper.getInstance().init(this.context)
  .then(() => hilog.info(..., 'DatabaseHelper initialized successfully'))
  .catch((err) => hilog.error(..., 'DatabaseHelper init failed: ...'));
```
采用异步 `.then/.catch`，不阻塞 UI 启动流程，符合官方 Stage 模型最佳实践。

**`onDestroy` 末尾新增数据库关闭：**
```typescript
DatabaseHelper.getInstance().close();
```
确保应用退出时 RdbStore 资源正常释放，防止数据库文件损坏。

---

### 3.2 `entry/src/main/ets/pages/MqttManager.ets`（修改，360 行）

**修改内容：**

**新增 import：**
```typescript
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
```

**`addFallRecord()` 方法末尾追加持久化：**
```typescript
const event: HealthEvent = {
  eventType: 'fall', eventTime: timestamp,
  dateStr, timeStr, severity: 3, isHandled: 0,
};
DatabaseHelper.getInstance().insertHealthEvent(event)
  .then(rowId => console.log(`ArkDB 写入摔倒事件 rowId=${rowId}`))
  .catch(e => console.error(`ArkDB 写入摔倒事件失败 ${e.message}`));
```

**`addSedentaryRecord()` 方法末尾追加持久化（severity: 1，久坐低危）**

**`clearFallRecords()` 同步清库：**
```typescript
DatabaseHelper.getInstance().clearAllHealthEvents()
```

**设计原则：** MQTT 回调不 await 数据库写入（fire-and-forget），避免阻塞实时告警 UI 更新。

---

## 四、文件结构变化

```
entry/src/main/ets/
├── database/                    ← 【新建目录】
│   └── DatabaseHelper.ets       ← 【新建文件】556 行
├── entryability/
│   └── EntryAbility.ets         ← 【修改】新增 DB init/close
└── pages/
    └── MqttManager.ets          ← 【修改】addFallRecord/addSedentaryRecord 追加持久化
```

---

## 五、数据库初始化流程图

```
APP 启动
  └─ EntryAbility.onCreate()
       ├─ ThemeManager.init()
       └─ DatabaseHelper.init(context)        ← 异步，不阻塞 UI
            ├─ relationalStore.getRdbStore()   ← 获取或创建 GuardianStar.db
            └─ migrateDatabase()
                 ├─ createTransaction()
                 ├─ PRAGMA user_version = 0？
                 │   ├─ CREATE TABLE t_user
                 │   ├─ CREATE TABLE t_health_event
                 │   ├─ CREATE TABLE t_video_record
                 │   └─ PRAGMA user_version = 1
                 └─ transaction.commit()

MQTT 收到摔倒告警
  └─ MqttManager.addFallRecord(timestamp)
       ├─ 更新内存 fallRecords[]（触发 UI 响应式刷新）
       └─ DatabaseHelper.insertHealthEvent(event)  ← 异步持久化
```

---

## 六、后续使用示例

### 用户登录后保存账号信息
```typescript
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';

const user: UserInfo = {
  username: 'Frank',
  phone: '13800138000',
  passwordHash: 'sha256(password)',  // 调用方负责加密
  createTime: Date.now(),
};
await DatabaseHelper.getInstance().insertUser(user);
```

### record.ets 中从数据库加载历史记录
```typescript
aboutToAppear(): void {
  DatabaseHelper.getInstance().queryHealthEvents('fall')
    .then(events => {
      this.fallRecords = events.map(e => ({
        time: e.timeStr, date: e.dateStr, timestamp: e.eventTime
      }));
    });
}
```

### 插入视频记录（录像模块调用）
```typescript
await DatabaseHelper.getInstance().insertVideoRecord({
  filePath: '/data/storage/el2/base/videos/rec_20260321.mp4',
  durationSec: 120,
  fileSizeKb: 8192,
  recordTime: Date.now(),
  dateStr: '2026.03.21',
  isExported: 0,
});
```

---

## 七、注意事项

1. **密码存储：** `t_user.password_hash` 只存哈希值（如 SHA-256 + salt），
   明文密码绝不入库。当前 Login.ets 使用硬编码账号，接入真实注册/登录流程后需对接此字段。

2. **视频文件管理：** 数据库只存元数据（路径），视频二进制文件存放在应用沙箱
   `/data/storage/el2/base/` 下，滚动清理数据库记录后，需同步用 `fs` 模块删除物理文件。

3. **多 UIAbility：** 官方文档指出，不同 UIAbility 使用相同数据库名会产生多个独立数据库实例，
   守护星目前只有单 `EntryAbility`，无此问题。

4. **错误重建：** 若数据库出现 14800011 异常，按官方《关系型数据库异常重建》文档处理。

5. **升级数据库：** 在 `DatabaseHelper.migrateDatabase()` 追加 `if (version === 1)` 分支，
   用 `ALTER TABLE` 变更表结构，并更新 `PRAGMA user_version = 2`。
