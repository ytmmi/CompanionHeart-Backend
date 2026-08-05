/* 保存后的重启提醒条。
 *
 * 后端在启动时把配置读成了单例，改完磁盘不重启不会全部生效；
 * 但只改了 agent / llm 的话，重启 sidecar 就够 —— 它重启时会重读 llm 配置注入 env。
 */

import { postJSON } from '../core/api.js';
import { emit, EVT } from '../core/bus.js';
import { $, el } from '../core/dom.js';
import { toast } from '../core/toast.js';

export function showRestartBanner(modules) {
  clearRestartBanner();
  if (!modules.length) return;

  const banner = el('div', 'restart-banner');
  banner.id = 'restartBanner';
  banner.appendChild(el('span', null,
    '配置已写入磁盘。后端在启动时缓存了配置单例，需重启 uvicorn 才会全部生效。'));
  banner.appendChild(el('div', 'spacer'));

  if (modules.some(m => m === 'agent' || m === 'llm')) {
    const btn = el('button', 'btn sm', '重启 Agent sidecar');
    btn.addEventListener('click', () => restartAgent(btn, '重启 Agent sidecar'));
    banner.appendChild(btn);
  }

  const close = el('button', 'icon-btn', '✕');
  close.addEventListener('click', clearRestartBanner);
  banner.appendChild(close);

  $('#viewSimple').prepend(banner);
}

export function clearRestartBanner() {
  $('#restartBanner')?.remove();
}

export async function restartAgent(btn, label) {
  btn.disabled = true;
  btn.textContent = '重启中…';
  try {
    const r = await postJSON('/api/settings/agent-restart', {});
    toast(r.message, r.ok ? 'success' : 'error', 5200);
  } catch (e) {
    toast('重启失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = label;
    emit(EVT.STATUS_REFRESH);
  }
}
