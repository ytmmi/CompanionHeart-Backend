/* 插件卡片渲染 */

import { api } from '../core/api.js';
import { $, el } from '../core/dom.js';
import { state } from '../core/state.js';
import { renderPluginActions } from './pluginActions.js';

const TYPE_LABELS = { tts: 'TTS', asr: 'ASR', agent: 'Agent', llm: 'LLM' };

export async function loadPlugins() {
  const host = $('#pluginList');
  const loading = $('#pluginsLoading');
  if (loading) loading.classList.remove('hidden');
  try {
    const data = await api('/api/plugins');
    state.trashDir = data.trash_dir || '';
    renderPlugins(data.plugins || []);
  } catch (e) {
    host.innerHTML = '';
    host.appendChild(el('div', 'loading', '加载插件失败：' + e.message));
  } finally {
    if (loading) loading.classList.add('hidden');
  }
}

function renderPlugins(plugins) {
  const host = $('#pluginList');
  host.innerHTML = '';

  if (!plugins.length) {
    host.appendChild(el('div', 'loading', 'custom_plugin/ 下没有插件'));
    return;
  }

  plugins.forEach(p => host.appendChild(
    p.valid === false ? renderBrokenPlugin(p) : renderPluginCard(p)));
}

function renderBrokenPlugin(p) {
  const card = el('div', 'plugin-card broken');
  const head = el('div', 'pc-head');
  head.append(
    el('span', 'pc-name', p.name || p.dir || '(未知)'),
    el('span', 'pc-badge err', '无效'),
  );
  card.appendChild(head);
  card.appendChild(el('div', 'pc-desc', p.error || '无效插件目录'));
  return card;
}

function renderPluginCard(p) {
  const card = el('div', 'plugin-card');
  card.appendChild(renderHead(p));
  card.appendChild(renderMeta(p));
  if (p.description) card.appendChild(el('div', 'pc-desc', p.description));
  card.appendChild(renderDetail(p));
  card.appendChild(renderPluginActions(p));
  return card;
}

/** 名称 + 类型 + 状态灯 + 自启标记 */
function renderHead(p) {
  const head = el('div', 'pc-head');
  head.appendChild(el('span', 'pc-name', p.name));
  head.appendChild(el('span', `pc-badge ${p.type}`, TYPE_LABELS[p.type] || p.type || '?'));

  const dot = el('span', 'pc-dot ' + (p.running ? (p.healthy ? 'online' : 'warn') : 'offline'));
  const statusText = p.running ? (p.healthy ? '运行中' : '端口占用（健康检查未过）') : '已停止';
  const st = el('span', 'pc-status');
  st.append(dot, el('span', null, statusText));
  head.appendChild(st);

  head.appendChild(el('div', 'spacer'));
  if (p.autostart) {
    const b = el('span', 'pc-tag', '随后端自启');
    b.title = '配置里 ' + (p.autostart_reason || '') + ' —— 后端启动时会拉起它';
    head.appendChild(b);
  }
  return head;
}

function renderMeta(p) {
  const meta = el('div', 'pc-meta');
  meta.appendChild(el('span', null, `v${p.version || '?'}`));
  if (p.port) meta.appendChild(el('span', 'mono', `:${p.port}`));
  meta.appendChild(el('span', null, `目录 ${p.dir}`));
  if (p.author) meta.appendChild(el('span', null, p.author));
  if (p.pid && p.pid.length) meta.appendChild(el('span', 'mono', `PID ${p.pid.join(',')}`));
  return meta;
}

/** 端点 / 依赖 / 仓库 */
function renderDetail(p) {
  const detail = el('div', 'pc-detail');

  const eps = Object.entries(p.endpoints || {});
  if (eps.length) {
    const row = el('div', 'pc-chips');
    row.appendChild(el('span', 'pc-chips-lbl', '端点'));
    eps.forEach(([k, v]) => {
      const chip = el('span', 'pc-chip mono', v);
      chip.title = k;
      row.appendChild(chip);
    });
    detail.appendChild(row);
  }

  if ((p.dependencies || []).length) {
    const row = el('div', 'pc-chips');
    row.appendChild(el('span', 'pc-chips-lbl', '依赖'));
    p.dependencies.forEach(d => row.appendChild(el('span', 'pc-chip mono', d)));
    detail.appendChild(row);
  }

  if (p.repository) {
    const row = el('div', 'pc-chips');
    row.appendChild(el('span', 'pc-chips-lbl', '仓库'));
    const a = el('a', 'pc-link', p.repository);
    a.href = p.repository; a.target = '_blank'; a.rel = 'noopener';
    row.appendChild(a);
    detail.appendChild(row);
  }

  return detail;
}
