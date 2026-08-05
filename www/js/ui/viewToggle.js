/* 简单 / 高级 / 插件三视图切换。
 *
 * 简单与高级共用同一份 dirty 表，切过来必须重绘，否则未保存的改动显示不出来。
 */

import { emit, EVT } from '../core/bus.js';
import { $, $$ } from '../core/dom.js';
import { state } from '../core/state.js';
import { renderAdvanced } from '../settings/advanced.js';
import { renderGroups } from '../settings/groups.js';

export function initViewToggle() {
  $$('.vt-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.vt-btn').forEach(b => b.classList.toggle('active', b === btn));
      state.view = btn.dataset.view;
      $('#viewSimple').classList.toggle('hidden', state.view !== 'simple');
      $('#viewAdvanced').classList.toggle('hidden', state.view !== 'advanced');
      $('#viewPlugins').classList.toggle('hidden', state.view !== 'plugins');
      localStorage.setItem('ch-view', state.view);

      if (state.view === 'plugins') { emit(EVT.PLUGINS_RELOAD); return; }
      if (!state.schema) return;
      if (state.view === 'advanced') renderAdvanced();
      else renderGroups();
      emit(EVT.DIRTY_CHANGED);  // 重绘后补上 dirty 高亮
    });
  });

  const saved = localStorage.getItem('ch-view');
  if (saved === 'advanced' || saved === 'plugins') {
    $(`.vt-btn[data-view="${saved}"]`)?.click();
  }
}
