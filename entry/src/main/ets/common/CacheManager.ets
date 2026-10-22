import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';
import webview from '@ohos.web.webview';
import { BusinessError } from '@kit.BasicServicesKit';

export interface CacheStats {
  bytes: number;
  files: number;
  skipped: number;
  failed: number;
}

export interface CacheClearResult {
  releasedBytes: number;
  deletedFiles: number;
  failed: number;
  skipped: number;
  remaining: CacheStats;
  webCacheRequested: boolean;
}

interface CacheFile {
  path: string;
  root: string;
}

interface CacheInventory {
  stats: CacheStats;
  entries: CacheFile[];
}

/** Only disposable app cache/temp files. Never touch filesDir, databases or preferences. */
export class CacheManager {
  private static instance: CacheManager = new CacheManager();
  private activeFiles: Set<string> = new Set<string>();
  private clearing: Promise<CacheClearResult> | undefined = undefined;

  public static getInstance(): CacheManager { return CacheManager.instance; }

  public async retain(path: string): Promise<void> {
    // New writers wait for an in-progress cleanup before opening their file.
    if (this.clearing !== undefined) await this.clearing;
    this.activeFiles.add(path);
  }
  public release(path: string): void { this.activeFiles.delete(path); }

  public formatBytes(bytes: number): string {
    if (bytes < 1024) return `${Math.max(0, Math.floor(bytes))} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }

  private missing(error: BusinessError): boolean { return error.code === 13900002; }

  private roots(context: common.UIAbilityContext): string[] {
    const roots: string[] = [];
    const application = context.getApplicationContext();
    const candidates: string[] = [context.cacheDir, context.tempDir, application.cacheDir, application.tempDir]
      .sort((first: string, second: string): number => first.length - second.length);
    for (const candidate of candidates) {
      const root = candidate.replace(/\/+$/, '');
      if (!root.startsWith('/') || root === '/' || root.includes('/../') || root.includes('/./')) continue;
      if (!roots.some((existing: string): boolean => root === existing || root.startsWith(existing + '/'))) roots.push(root);
    }
    return roots;
  }

  private inside(path: string, root: string): boolean {
    return path.startsWith(root + '/') && !path.includes('/../') && !path.includes('/./');
  }

  private reserved(name: string): boolean {
    // Web resource cache uses its native API; shader caches belong to the running renderer.
    return ['web', 'arkweb', 'webview', 'blobshader', 'ddkshader'].includes(name.toLowerCase());
  }

  private async scanDirectory(root: string, directory: string, inventory: CacheInventory): Promise<void> {
    let names: string[];
    try { names = await fs.listFile(directory); }
    catch (error) {
      if (!this.missing(error as BusinessError)) inventory.stats.failed++;
      return;
    }
    for (const name of names) {
      if (name === '.' || name === '..' || name.includes('/')) { inventory.stats.skipped++; continue; }
      const path = `${directory}/${name}`;
      if (!this.inside(path, root) || this.activeFiles.has(path) || this.reserved(name)) {
        inventory.stats.skipped++;
        continue;
      }
      try {
        const stat = await fs.lstat(path);
        if (stat.isSymbolicLink()) { inventory.stats.skipped++; continue; }
        if (stat.isDirectory()) await this.scanDirectory(root, path, inventory);
        else if (stat.isFile()) {
          inventory.stats.bytes += stat.size;
          inventory.stats.files++;
          inventory.entries.push({ path: path, root: root });
        } else inventory.stats.skipped++;
      } catch (error) {
        if (!this.missing(error as BusinessError)) inventory.stats.failed++;
      }
    }
  }

  private async inventory(context: common.UIAbilityContext): Promise<CacheInventory> {
    const inventory: CacheInventory = { stats: { bytes: 0, files: 0, skipped: 0, failed: 0 }, entries: [] };
    for (const root of this.roots(context)) {
      try {
        const stat = await fs.lstat(root);
        if (stat.isDirectory() && !stat.isSymbolicLink()) await this.scanDirectory(root, root, inventory);
        else inventory.stats.failed++;
      } catch (error) {
        if (!this.missing(error as BusinessError)) inventory.stats.failed++;
      }
    }
    return inventory;
  }

  public async measure(context: common.UIAbilityContext): Promise<CacheStats> {
    return (await this.inventory(context)).stats;
  }

  public clear(context: common.UIAbilityContext): Promise<CacheClearResult> {
    if (this.clearing !== undefined) return this.clearing;
    this.clearing = this.clearFiles(context);
    return this.clearing;
  }

  private async clearFiles(context: common.UIAbilityContext): Promise<CacheClearResult> {
    let releasedBytes = 0;
    let deletedFiles = 0;
    let failed = 0;
    let skipped = 0;
    let webCacheRequested = false;
    try {
      const before = await this.inventory(context);
      failed = before.stats.failed;
      skipped = before.stats.skipped;
      for (const entry of before.entries) {
        if (!this.inside(entry.path, entry.root) || this.activeFiles.has(entry.path)) { skipped++; continue; }
        try {
          // Recheck every parent: never follow a directory swapped for a symlink after scanning.
          const relative = entry.path.slice(entry.root.length + 1).split('/');
          let parent = entry.root;
          let safe = true;
          for (let index = 0; index < relative.length - 1; index++) {
            parent += '/' + relative[index];
            const parentStat = await fs.lstat(parent);
            if (!parentStat.isDirectory() || parentStat.isSymbolicLink()) { safe = false; break; }
          }
          if (!safe || this.activeFiles.has(entry.path)) { skipped++; continue; }
          const stat = await fs.lstat(entry.path);
          if (!stat.isFile() || stat.isSymbolicLink() || this.activeFiles.has(entry.path)) { skipped++; continue; }
          await fs.unlink(entry.path);
          releasedBytes += stat.size;
          deletedFiles++;
        } catch (error) {
          if (!this.missing(error as BusinessError)) failed++;
        }
      }
      try { webview.WebviewController.removeAllCache(true); webCacheRequested = true; }
      catch (_error) { failed++; }
      const remaining = await this.measure(context);
      return { releasedBytes, deletedFiles, failed, skipped, remaining, webCacheRequested };
    } finally { this.clearing = undefined; }
  }
}
