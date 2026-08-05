/* 插件卡片上的操作：启动 / 停止 / 日志 / 卸载 */

import { postJSON } from '../core/api.js';
import { emit, EVT } from '../core/bus.js';
import { el } from '../core/dom.js';
import { toast } from '../core/toast.js';
import { openJobConsole } from './jobConsole.js';
import { openPluginLogs } from './logViewer.js';

export function renderPluginActions(p) {
  const bar = el('div', 'pc-actions');

  if (p.running) {
    const stop = el('button', 'btn sm', '停止');
    stop.addEventListener('click', () => doStopPlugin(p));
    bar.appendChild(stop);
  } else {
    const start = el('button', 'btn sm primary', '启动');
    start.addEventListener('click', () => doStartPlugin(p));
    bar.appendChild(start);
  }

  const logs = el('button', 'btn sm ghost', '日志');
  logs.addEventListener('click', () => openPluginLogs(p.dir));
  bar.appendChild(logs);

  bar.appendChild(el('div', 'spacer'));

  const un = el('button', 'btn sm danger-ghost', '卸载');
  un.disabled = p.running;
  un.title = p.running ? '运行中不可卸载，请先停止' : '移入 .trash（可逆）';
  un.addEventListener('click', () => doUninstallPlugin(p));
  bar.appendChild(un);

  return bar;
}

async function doStartPlugin(p) {
  // agent 需要后端注入 env，这里也能起（复刻了 env），但给个提示
  if (p.type === 'agent') {
    if (!confirm(`启动 ${p.name}？\n\n它需要 LLM 配置作为环境变量，面板会按 llm/config.yaml 复刻注入。\n` +
                 `若要让后端完全接管，建议改用「人格与代理」里的「重启 sidecar」。`)) return;
  }
  try {
    const r = await postJSON('/api/plugins/start', { name: p.dir });
    if (r.already) { toast(r.message, 'info'); emit(EVT.PLUGINS_RELOAD); return; }
    if (!r.ok) throw new Error(r.error);
    openJobConsole(r.job, `启动 ${p.name}`);
  } catch (e) {
    toast('启动失败：' + e.message, 'error', 5200);
  }
}

async function doStopPlugin(p) {
  let msg = `停止 ${p.name}（:${p.port}）？`;
  if (p.autostart) {
    msg += `\n\n注意：它在配置里是自启的（${p.autostart_reason}）。停止后，` +
           `后端下次调用它可能报错，直到重启后端或重新启动它。`;
  }
  if (!confirm(msg)) return;
  try {
    const r = await postJSON('/api/plugins/stop', { name: p.dir });
    if (!r.ok) throw new Error(r.error);
    toast(r.message, 'success', 5200);
    emit(EVT.PLUGINS_RELOAD);
    emit(EVT.STATUS_REFRESH);
  } catch (e) {
    toast('停止失败：' + e.message, 'error', 5200);
  }
}

async function doUninstallPlugin(p) {
  if (!confirm(`卸载 ${p.name}？\n\n目录会移到 custom_plugin/.trash/（可恢复），不会硬删除。\n` +
               `依赖不会从 venv 卸载。`)) return;
  try {
    const r = await postJSON('/api/plugins/uninstall', { name: p.dir });
    if (!r.ok) throw new Error(r.error);
    toast(r.message, 'success', 6500);
    emit(EVT.PLUGINS_RELOAD);
  } catch (e) {
    toast('卸载失败：' + e.message, 'error', 5200);
  }
}
