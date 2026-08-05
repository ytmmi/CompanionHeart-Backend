/* ══════════════════════════════════════════════════════════
   CompanionHeart 设置页入口

   数据流：
     /api/settings/schema  → 简单视图（分组表单，带类型与校验）
     /api/settings/keys    → 高级视图（全部 key 的扁平编辑器）
   两个视图共用一份 dirty 表，保存时一起提交到 POST /api/settings/keys。

   模块划分（见各文件顶部注释）：
     core/     总线、DOM、API、状态、toast —— 不依赖任何业务模块
     ui/       主题、状态灯、视图切换、未保存改动条
     settings/ 简单视图与高级视图、备份抽屉、重启提醒
     plugins/  插件列表与操作、安装面板、任务控制台、日志查看

   模块之间只通过 core/bus.js 的事件互相通知，依赖图保持无环。
   ══════════════════════════════════════════════════════════ */

import { api } from './core/api.js';
import { emit, on, EVT } from './core/bus.js';
import { $ } from './core/dom.js';
import { adoptSnapshot, state } from './core/state.js';
import { toast } from './core/toast.js';

import { initInstallPanel } from './plugins/installPanel.js';
import { loadPlugins } from './plugins/pluginList.js';

import { renderAdvanced, applySearch } from './settings/advanced.js';
import { initBackupDrawer } from './settings/backupDrawer.js';
import { renderGroups } from './settings/groups.js';
import { showRestartBanner } from './settings/restartBanner.js';

import { renderDirtyBar, revert, save } from './ui/dirtyBar.js';
import { refreshStatus } from './ui/status.js';
import { initTheme } from './ui/theme.js';
import { initViewToggle } from './ui/viewToggle.js';

// ── 事件接线 ──

function wireBus() {
  on(EVT.DIRTY_CHANGED,  renderDirtyBar);
  on(EVT.STATUS_REFRESH, refreshStatus);
  on(EVT.PLUGINS_RELOAD, loadPlugins);
  on(EVT.RESTART_HINT,   showRestartBanner);
  on(EVT.CONFIG_RELOAD,  loadAll);
  on(EVT.RERENDER,       rerender);
}

/** 从磁盘重新拉全量配置并重绘 */
async function loadAll() {
  const [schema, keys] = await Promise.all([
    api('/api/settings/schema'),
    api('/api/settings/keys'),
  ]);
  adoptSnapshot(schema, keys);

  // 角色情感表：供试听的情感 chip 使用
  try {
    const v = await api('/api/settings/tts-voices');
    state.schema._characters = v.voices.filter(x => x.category === 'plugin');
  } catch {
    state.schema._characters = [];
  }

  $('#schemaLoading')?.remove();
  rerender();
}

/** 用现有 state 重绘两个视图 */
function rerender() {
  renderGroups();
  renderAdvanced();
  renderDirtyBar();
}

// ── 全局快捷键与离开确认 ──

function initGuards() {
  window.addEventListener('beforeunload', e => {
    if (state.dirty.size) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      save();
    }
  });

  $('#saveBtn').addEventListener('click', save);
  $('#revertBtn').addEventListener('click', revert);
  $('#searchInput').addEventListener('input', applySearch);
}

// ── 启动 ──

(async function init() {
  wireBus();
  initTheme();
  initViewToggle();
  initGuards();
  initBackupDrawer();
  initInstallPanel();

  try {
    await loadAll();
  } catch (e) {
    const l = $('#schemaLoading');
    if (l) l.textContent = '加载配置失败：' + e.message;
    toast('加载配置失败：' + e.message, 'error', 8000);
  }

  refreshStatus();
  setInterval(refreshStatus, 8000);
})();
