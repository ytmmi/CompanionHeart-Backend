/* 底部「未保存改动」条：计数、提示写入哪些文件、保存 / 撤销 */

import { postJSON } from '../core/api.js';
import { emit, emitAsync, EVT } from '../core/bus.js';
import { $, $$ } from '../core/dom.js';
import { clearDirty, MODULE_FILES, state } from '../core/state.js';
import { toast } from '../core/toast.js';

export function renderDirtyBar() {
  const bar = $('#dirtyBar');
  const n = state.dirty.size;
  bar.classList.toggle('hidden', n === 0);
  syncDirtyClasses();
  if (!n) return;

  $('#dirtyCount').textContent = `${n} 项未保存`;
  const mods = [...new Set([...state.dirty.keys()].map(k => k.split('.')[0]))];
  $('#dirtyHint').textContent =
    `将写入 ${mods.map(m => MODULE_FILES[m]).join('、')}（保存前自动备份，注释会保留）`;
}

/** 给改动过的字段加高亮 class */
function syncDirtyClasses() {
  $$('[data-fieldkey]').forEach(n => {
    n.classList.toggle('dirty', state.dirty.has(n.dataset.fieldkey));
  });
}

export async function save() {
  if (!state.dirty.size) return;
  const btn = $('#saveBtn');
  btn.disabled = true;
  btn.textContent = '保存中…';

  const payload = Object.fromEntries(state.dirty);
  try {
    const r = await postJSON('/api/settings/keys', payload);
    if (!r.ok) throw new Error(r.error || '保存失败');

    (r.warnings || []).forEach(w => toast('⚠ ' + w, 'warn', 6500));
    (r.port_syncs || []).forEach(s => toast(s, 'info', 5200));
    toast(`已保存 ${Object.keys(payload).length} 项到 ${(r.updated_modules || []).join('、')}`,
          'success');

    // 重新拉取，确保界面显示的是磁盘真实值（类型会被归一化）
    state.dirty.clear();
    await emitAsync(EVT.CONFIG_RELOAD);
    emitAsync(EVT.RESTART_HINT, r.updated_modules || []);
  } catch (e) {
    toast('保存失败：' + e.message, 'error', 6000);
  } finally {
    btn.disabled = false;
    btn.textContent = '保存';
  }
}

export function revert() {
  if (!state.dirty.size) return;
  if (!confirm(`撤销 ${state.dirty.size} 项未保存的改动？`)) return;
  clearDirty();
  emit(EVT.RERENDER);
}
