import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import { util } from '@kit.ArkTS';
import { STORE_KEY_AVATAR } from '../config';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { CloudService } from './CloudService';

/** 将云端头像版本落到当前设备的私有缓存。 */
export class AvatarSyncService {
  static async sync(context: common.UIAbilityContext, identifier: string,
    localUser?: UserInfo): Promise<void> {
    const user = localUser ?? await DatabaseHelper.getInstance().queryUserByIdentifier(identifier);
    if (!user) return;

    const result = await CloudService.getInstance().downloadAvatar();
    if (!result.success) return;
    let file: fs.File | undefined;
    try {
      const avatarDir = context.filesDir + '/avatars';
      try { fs.mkdirSync(avatarDir); } catch (_e) {}
      const oldPath = user.avatarPath || '';
      if (result.hasAvatar === false) {
        user.avatarPath = '';
        await DatabaseHelper.getInstance().updateUser(user);
        AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, '');
        if (oldPath.startsWith(avatarDir + '/')) {
          try { fs.unlinkSync(oldPath); } catch (_e) {}
        }
        return;
      }
      if (!result.imageBase64) return;
      const bytes = new util.Base64Helper().decodeSync(result.imageBase64);
      const path = avatarDir + '/cloud_avatar_' + Date.now() + '.jpg';
      file = fs.openSync(path, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
      fs.writeSync(file.fd, bytes.buffer);
      fs.closeSync(file);
      file = undefined;
      user.avatarPath = path;
      await DatabaseHelper.getInstance().updateUser(user);
      AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, path);
      if (oldPath.startsWith(avatarDir + '/') && oldPath !== path) {
        try { fs.unlinkSync(oldPath); } catch (_e) {}
      }
    } catch (e) {
      console.warn('[AvatarSyncService]: 云端头像同步失败 ' + JSON.stringify(e));
    } finally {
      if (file !== undefined) { try { fs.closeSync(file); } catch (_e) {} }
    }
  }
}
