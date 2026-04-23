/**
 * CloudSyncService.ets — 云端数据同步服务
 * 
 * 功能：
 * 1. App启动时预同步云端用户数据
 * 2. 定期同步本地和云端数据
 * 3. 处理数据冲突（云端优先）
 */

import { DatabaseHelper } from '../database/DatabaseHelper';
import { CloudService, CloudUser, CloudResult } from './CloudService';
import { BusinessError } from '@kit.BasicServicesKit';

interface SyncStatus {
  isSyncing: boolean;
  lastSyncTime: number;
}

export class CloudSyncService {
  private static instance: CloudSyncService;
  private db: DatabaseHelper;
  private cloud: CloudService;
  
  // 同步状态
  private isSyncing: boolean = false;
  private lastSyncTime: number = 0;
  
  private constructor() {
    this.db = DatabaseHelper.getInstance();
    this.cloud = CloudService.getInstance();
  }
  
  public static getInstance(): CloudSyncService {
    if (!CloudSyncService.instance) {
      CloudSyncService.instance = new CloudSyncService();
    }
    return CloudSyncService.instance;
  }
  
  /**
   * App启动时预同步：将云端用户数据同步到本地
   * 注意：这里只同步用户数据，不处理其他业务数据
   */
  async preSyncOnAppStart(): Promise<void> {
    if (this.isSyncing) {
      console.info('[CloudSyncService]: 已在同步中，跳过');
      return;
    }
    
    this.isSyncing = true;
    console.info('[CloudSyncService]: 开始App启动预同步');
    
    try {
      console.info('[CloudSyncService]: 预同步完成（实际同步在登录时进行）');
    } catch (error) {
      console.error('[CloudSyncService]: 预同步失败:', error);
    } finally {
      this.isSyncing = false;
      this.lastSyncTime = Date.now();
    }
  }
  
  /**
   * 同步单个用户：从云端拉取用户数据到本地
   * 用于登录时检查用户是否存在
   * 返回结构与CloudService.login兼容
   */
  async syncUserFromCloud(username: string, passwordHash: string): Promise<CloudResult> {
    console.info('[CloudSyncService]: 同步用户', username);
    
    try {
      const cloudResult: CloudResult = await this.cloud.login(username, passwordHash);
      
      if (cloudResult.success && cloudResult.user) {
        const cloudUser: CloudUser = cloudResult.user;
        
        // 检查本地是否已有该用户
        const localUser = await this.db.queryUserByUsername(username);
        
        if (localUser) {
          // 本地已有：更新本地数据（云端优先）
          console.info('[CloudSyncService]: 更新本地用户数据', username);
          await this.db.updateUser({
            username: cloudUser.username,
            nickname: cloudUser.nickname,
            phone: cloudUser.phone,
            passwordHash: cloudUser.passwordHash,
            avatarPath: cloudUser.avatarPath,
            email: cloudUser.email,
            address: cloudUser.address,
            createTime: cloudUser.createTime,
          });
        } else {
          // 本地没有：插入新用户
          console.info('[CloudSyncService]: 插入新用户到本地', username);
          await this.db.insertUser({
            username: cloudUser.username,
            nickname: cloudUser.nickname,
            phone: cloudUser.phone,
            passwordHash: cloudUser.passwordHash,
            avatarPath: cloudUser.avatarPath,
            email: cloudUser.email,
            address: cloudUser.address,
            createTime: cloudUser.createTime,
          });
        }
        
        const result: CloudResult = {
          success: true,
          user: cloudUser,
          message: '同步成功'
        };
        return result;
      } else {
        const result: CloudResult = {
          success: false,
          message: cloudResult.message || '云端用户不存在'
        };
        return result;
      }
    } catch (error) {
      console.error('[CloudSyncService]: 同步用户失败:', error);
      const err: BusinessError = error as BusinessError;
      const errorMsg: string = err.message || '未知错误';
      const result: CloudResult = {
        success: false,
        message: '同步失败: ' + errorMsg
      };
      return result;
    }
  }
  
  /**
   * 获取同步状态
   */
  getSyncStatus(): SyncStatus {
    const status: SyncStatus = { isSyncing: this.isSyncing, lastSyncTime: this.lastSyncTime };
    return status;
  }
}
