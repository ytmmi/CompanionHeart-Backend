/* 分组底部的操作栏：测试连接、试听、重启 sidecar、备份 / 恢复 */

import { postJSON } from '../core/api.js';
import { emit, EVT } from '../core/bus.js';
import { $, el } from '../core/dom.js';
import { currentValue, state } from '../core/state.js';
import { openBackups } from './backupDrawer.js';
import { restartAgent } from './restartBanner.js';

export function renderGroupActions(g) {
  const bar = el('div', 'group-actions');
  const result = el('div', 'test-result');
  const audioBox = el('div', 'preview-audio');

  if (g.test) bar.appendChild(makeTestButton(g, result));
  if (g.preview) bar.appendChild(makePreviewButton(result, audioBox));

  (g.actions || []).forEach(a => {
    if (a.id !== 'restart-agent') return;
    const btn = el('button', 'btn', a.label);
    btn.addEventListener('click', () => restartAgent(btn, a.label));
    bar.appendChild(btn);
  });

  bar.appendChild(el('div', 'spacer'));

  const bk = el('button', 'btn ghost sm', '备份 / 恢复');
  bk.addEventListener('click', () => openBackups(g.id));
  bar.appendChild(bk);

  bar.append(result, audioBox);
  return bar;
}

function makeTestButton(g, result) {
  const btn = el('button', 'btn', '测试连接');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '测试中…';
    result.className = 'test-result';
    result.textContent = '';
    try {
      const r = await postJSON('/api/settings/test', { module: g.test });
      result.className = `test-result ${r.ok ? 'ok' : (r.level === 'warn' ? 'warn' : 'error')}`;
      result.textContent = (r.ok ? '✓ ' : '✕ ') + r.message;
      if (state.dirty.size) {
        result.textContent += '（测的是磁盘上已保存的配置，未保存的改动不算）';
      }
    } catch (e) {
      result.className = 'test-result error';
      result.textContent = '✕ ' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = '测试连接';
      emit(EVT.STATUS_REFRESH);
    }
  });
  return btn;
}

function makePreviewButton(result, audioBox) {
  const btn = el('button', 'btn', '试听');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '合成中…';
    audioBox.innerHTML = '';
    result.textContent = '';
    try {
      const r = await fetch('/api/settings/tts-preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectPreviewBody()),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${r.status}`);
      }

      const blob = await r.blob();
      const audio = el('audio');
      audio.controls = true;
      audio.autoplay = true;
      audio.src = URL.createObjectURL(blob);
      audioBox.appendChild(audio);
    } catch (e) {
      result.className = 'test-result error';
      result.textContent = '✕ 试听失败：' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = '试听';
    }
  });
  return btn;
}

/** 试听用界面上的当前值（含未保存的），这样不用先保存就能听效果 */
function collectPreviewBody() {
  const mode = String(currentValue('tts.mode') || 'plugin');
  const body = { mode };

  if (mode === 'plugin') {
    body.character_name = currentValue('tts.plugin.config.character_name');
    const active = $('.emo-chip.active');
    if (active) body.emotion = active.dataset.emo;
  } else if (mode === 'edge') {
    body.voice  = currentValue('tts.edge.voices.zh.voice');
    body.rate   = currentValue('tts.edge.default_params.rate');
    body.volume = currentValue('tts.edge.default_params.volume');
    body.pitch  = currentValue('tts.edge.default_params.pitch');
  }
  return body;
}
