/* 顶部服务状态灯 */

import { api } from '../core/api.js';
import { $, el } from '../core/dom.js';

export async function refreshStatus() {
  let data;
  try {
    data = await api('/api/settings/status');
  } catch { return; }

  const bar = $('#statusBar');
  bar.innerHTML = '';
  data.services.forEach(s => {
    const item = el('div', `status-item${s.muted ? ' muted' : ''}`);
    item.title = s.muted
      ? `${s.label} 已在配置中关闭`
      : `${s.label} — 端口 ${s.port || '未知'} ${s.online ? '在线' : '离线'}`;
    item.appendChild(el('span', `status-dot ${s.online ? 'online' : 'offline'}`));
    item.appendChild(el('span', null, s.label));
    if (s.port) item.appendChild(el('span', 'port', `:${s.port}`));
    bar.appendChild(item);
  });
}
