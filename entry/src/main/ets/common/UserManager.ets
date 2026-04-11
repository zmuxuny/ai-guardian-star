/**
 * UserManager.ets — 统一用户管理工具
 * 确保整个应用中用户名获取的一致性
 */

export class UserManager {
  private static instance: UserManager;
  
  // AppStorage key for logged in user
  private static readonly STORAGE_KEY = 'loggedInUsername';
  
  // 默认用户名，用于未登录状态
  private static readonly DEFAULT_USERNAME = 'default_user';
  
  private constructor() {}
  
  public static getInstance(): UserManager {
    if (!UserManager.instance) {
      UserManager.instance = new UserManager();
    }
    return UserManager.instance;
  }
  
  /**
   * 获取当前登录用户名（统一入口，保证一致性）
   * @returns 当前用户名，未登录时返回默认用户名
   */
  public getCurrentUsername(): string {
    return AppStorage.get<string>(UserManager.STORAGE_KEY) ?? UserManager.DEFAULT_USERNAME;
  }
  
  /**
   * 设置当前登录用户名
   * @param username 用户名
   */
  public setCurrentUsername(username: string): void {
    AppStorage.setOrCreate<string>(UserManager.STORAGE_KEY, username);
  }
  
  /**
   * 清除当前登录用户名（退出登录时使用）
   */
  public clearCurrentUsername(): void {
    AppStorage.setOrCreate<string>(UserManager.STORAGE_KEY, '');
  }
  
  /**
   * 检查是否已登录
   * @returns true表示已登录，false表示未登录
   */
  public isLoggedIn(): boolean {
    const username = AppStorage.get<string>(UserManager.STORAGE_KEY);
    return username !== undefined && username.trim() !== '' && username !== UserManager.DEFAULT_USERNAME;
  }
  
  /**
   * 获取默认用户名
   * @returns 默认用户名
   */
  public getDefaultUsername(): string {
    return UserManager.DEFAULT_USERNAME;
  }
}
