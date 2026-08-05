/* 高级视图：4 个 config.yaml 的全部 key 扁平列表 + 模糊搜索。
 *
 * 这里不做取值校验（schema 里那套 min/max/options 都不适用），
 * 只按磁盘上原值的 JS 类型决定用开关还是输入框。
 */

import { $, $$, el } from '../core/dom.js';
import { currentValue, MODULE_FILES, setDirty, state } from '../core/state.js';
import { openBackups } from './backupDrawer.js';
import { makeEyeButton } from './fields.js';

export function renderAdvanced() {
  const host = $('#allKeysBody');
  host.innerHTML = '';

  const byModule = {};
  Object.entries(state.keys).forEach(([k, meta]) => {
    (byModule[k.split('.')[0]] ||= []).push([k, meta]);
  });

  Object.entries(byModule).forEach(([mod, entries]) => {
    const block = el('div', 'mod-block');
    block.appendChild(renderModuleHead(mod));
    entries.forEach(([key, meta]) => block.appendChild(renderAdvRow(key, meta)));
    host.appendChild(block);
  });

  applySearch();
}

function renderModuleHead(mod) {
  const head = el('div', 'mod-head');
  head.append(
    el('span', null, mod),
    el('span', 'path', MODULE_FILES[mod] || ''),
    el('div', 'spacer'),
  );
  const bk = el('button', 'btn ghost sm', '备份 / 恢复');
  bk.addEventListener('click', () => openBackups(mod));
  head.appendChild(bk);
  return head;
}

function renderAdvRow(key, meta) {
  const row = el('div', 'adv-row');
  row.dataset.fieldkey = key;
  row.dataset.search = (key + ' ' + (meta.description || '')).toLowerCase();

  const kbox = el('div', 'adv-key');
  kbox.appendChild(el('div', 'k', key));
  if (meta.description) kbox.appendChild(el('div', 'd', meta.description));
  row.appendChild(kbox);

  const vbox = el('div', 'adv-val');
  vbox.appendChild(buildAdvInput(key, meta.value));
  row.appendChild(vbox);
  return row;
}

function buildAdvInput(key, value) {
  const val = currentValue(key);

  if (typeof value === 'boolean') {
    const sw = el('label', 'switch');
    const cb = el('input');
    cb.type = 'checkbox';
    cb.checked = Boolean(val);
    cb.addEventListener('change', () => setDirty(key, cb.checked));
    sw.append(cb, el('span', 'track'));
    return sw;
  }

  // 密钥类字段默认打码，免得截图/录屏泄露
  if (/api_key|token|secret|password/i.test(key)) {
    const rowEl = el('div', 'pw-row');
    const inp = el('input');
    inp.type = 'password';
    inp.value = val ?? '';
    inp.addEventListener('input', () => setDirty(key, inp.value));
    rowEl.append(inp, makeEyeButton(inp));
    return rowEl;
  }

  const inp = el('input');
  inp.type = typeof value === 'number' ? 'number' : 'text';
  if (typeof value === 'number' && !Number.isInteger(value)) inp.step = 'any';
  inp.value = val ?? '';
  inp.addEventListener('input', () => setDirty(key, inp.value));
  return inp;
}

export function applySearch() {
  const q = ($('#searchInput').value || '').trim().toLowerCase();
  const total = Object.keys(state.keys).length;
  let shown = 0;

  $$('.adv-row').forEach(r => {
    const hit = !q || r.dataset.search.includes(q);
    r.classList.toggle('hidden', !hit);
    if (hit) shown++;
  });
  $$('.mod-block').forEach(b => {
    b.classList.toggle('hidden', !$$('.adv-row:not(.hidden)', b).length);
  });

  $('#resultCount').textContent = q
    ? `匹配 ${shown} / ${total} 项`
    : `共 ${total} 个配置项`;
}
