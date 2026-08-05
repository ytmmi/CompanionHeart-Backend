/* 插件日志查看（custom_plugin/.logs/<插件>.log 的尾部） */

import { api } from '../core/api.js';
import { $ } from '../core/dom.js';

export async function openPluginLogs(dir) {
  const viewer = $('#logViewer');
  const body = $('#lvBody');
  $('#lvTitle').textContent = `插件日志 — ${dir}`;
  body.textContent = '加载中…';
  viewer.classList.remove('hidden');

  const load = async () => {
    try {
      const r = await api(`/api/plugins/logs?name=${encodeURIComponent(dir)}&tail=400`);
      if (!r.ok) { body.textContent = '加载失败：' + (r.error || ''); return; }
      body.textContent = r.lines.length ? r.lines.join('\n') : (r.note || '（日志为空）');
      body.scrollTop = body.scrollHeight;
    } catch (e) {
      body.textContent = '加载失败：' + e.message;
    }
  };

  $('#lvRefresh').onclick = load;
  $('#lvClose').onclick = () => viewer.classList.add('hidden');
  load();
}
