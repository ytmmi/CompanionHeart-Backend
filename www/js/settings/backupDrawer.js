/* 备份 / 恢复抽屉 */

import { api, postJSON } from '../core/api.js';
import { emitAsync, EVT } from '../core/bus.js';
import { $, el } from '../core/dom.js';
import { clearDirty } from '../core/state.js';
import { toast } from '../core/toast.js';

export async function openBackups(module) {
  const drawer = $('#backupDrawer');
  const body = $('#bdBody');
  $('#bdTitle').textContent = `备份与恢复 — ${module}`;
  body.innerHTML = '<div class="bk-empty">加载中…</div>';
  drawer.classList.remove('hidden');

  let data;
  try {
    data = await api('/api/settings/backups');
  } catch (e) {
    body.innerHTML = '';
    body.appendChild(el('div', 'bk-empty', '加载失败：' + e.message));
    return;
  }

  const info = data[module] || { backups: [], has_example: false };
  body.innerHTML = '';

  if (info.has_example) body.appendChild(renderResetBox(module, drawer));

  if (!info.backups.length) {
    body.appendChild(el('div', 'bk-empty', '暂无备份 —— 每次保存前会自动生成'));
    return;
  }

  info.backups.forEach((b, i) => body.appendChild(renderBackupRow(module, b, i, drawer)));
}

function renderResetBox(module, drawer) {
  const box = el('div', 'bd-danger');
  box.appendChild(el('div', null,
    '重置为 config.example.yaml 会丢弃当前全部自定义值（含 API 密钥）。' +
    '重置前会自动备份一份当前配置。'));

  const btn = el('button', 'btn sm', '重置为默认');
  btn.style.marginTop = '8px';
  btn.addEventListener('click', async () => {
    if (!confirm(`确定把 ${module} 重置为 config.example.yaml 默认值？`)) return;
    try {
      const r = await postJSON('/api/settings/reset', { module });
      if (!r.ok) throw new Error(r.error);
      toast(`${module} 已重置（旧配置备份为 ${r.backup}）`, 'success', 5200);
      await afterRewrite(module, drawer);
    } catch (e) {
      toast('重置失败：' + e.message, 'error');
    }
  });
  box.appendChild(btn);
  return box;
}

function renderBackupRow(module, b, index, drawer) {
  const row = el('div', 'bk-row');
  row.appendChild(el('span', 't', b.time));
  row.appendChild(el('span', 's', `${b.size} B${index === 0 ? ' · 最近一次' : ''}`));

  const btn = el('button', 'btn sm', '恢复');
  btn.addEventListener('click', async () => {
    if (!confirm(`用 ${b.time} 的备份覆盖当前 ${module} 配置？\n（当前配置会先被备份）`)) return;
    try {
      const r = await postJSON('/api/settings/restore', { module, file: b.file });
      if (!r.ok) throw new Error(r.error);
      toast(`${module} 已恢复到 ${b.time}`, 'success');
      await afterRewrite(module, drawer);
    } catch (e) {
      toast('恢复失败：' + e.message, 'error');
    }
  });
  row.appendChild(btn);
  return row;
}

/** 恢复 / 重置都会整体改写磁盘上的配置，界面必须丢掉 dirty 重新拉一遍 */
async function afterRewrite(module, drawer) {
  drawer.classList.add('hidden');
  clearDirty();
  await emitAsync(EVT.CONFIG_RELOAD);
  emitAsync(EVT.RESTART_HINT, [module]);
}

export function initBackupDrawer() {
  $('#bdClose').addEventListener('click', () => $('#backupDrawer').classList.add('hidden'));
  $('#backupDrawer').addEventListener('click', e => {
    if (e.target.id === 'backupDrawer') e.target.classList.add('hidden');
  });
}
