import { CloudService } from './CloudService';
import { DatabaseHelper } from '../database/DatabaseHelper';
import { UserManager } from './UserManager';

export interface SavedAddress {
  id: number;
  label: string;
  detail: string;
  latitude: number | null;
  longitude: number | null;
  isDefault: boolean;
  version: number;
}

export interface AddressResult {
  success: boolean;
  message?: string;
  addresses: SavedAddress[];
  defaultAddress: string;
}

export interface AddressDraft {
  id?: number;
  version?: number;
  label: string;
  detail: string;
  latitude: number | null;
  longitude: number | null;
  isDefault: boolean;
}

export interface AddressIdentity { id: number; version: number; }
class EmptyAddressQuery {}

export class AddressService {
  public static async request(action: string, body: Object): Promise<AddressResult> {
    const response = await CloudService.getInstance().authenticatedPost('/api/addresses/' + action, body);
    if (response.responseCode === 0) throw new Error('网络不可用，请联网后重试');
    if (response.responseCode === 404 && action === 'list') throw new Error('地址服务尚未接通');
    let result: AddressResult;
    try { result = JSON.parse(response.result) as AddressResult; }
    catch (_error) { throw new Error('地址服务响应异常，请稍后重试'); }
    if (response.responseCode !== 200 || !result.success || !Array.isArray(result.addresses)) {
      throw new Error(result.message || '地址操作失败，请重试');
    }
    return result;
  }

  public static async list(): Promise<AddressResult> { return AddressService.request('list', new EmptyAddressQuery()); }

  public static async cache(username: string, result: AddressResult): Promise<boolean> {
    if (UserManager.getInstance().getCurrentUsername() !== username) return false;
    try {
      await DatabaseHelper.getInstance().saveAddressSnapshot(username, JSON.stringify(result), result.defaultAddress);
      return true;
    } catch (_error) { return false; }
  }

  public static async cached(username: string): Promise<SavedAddress[] | null> {
    const value = await DatabaseHelper.getInstance().loadSetting(username, 'saved_addresses_v1');
    if (value === null) return null;
    try {
      const result = JSON.parse(value) as AddressResult;
      return Array.isArray(result.addresses) ? result.addresses : null;
    } catch (_error) { return null; }
  }
}
