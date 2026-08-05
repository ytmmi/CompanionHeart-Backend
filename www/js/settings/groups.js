/* 简单视图：按 schema 渲染分组卡片与字段行 */

import { $, $$, el } from '../core/dom.js';
import { state } from '../core/state.js';
import { applyConditionalVisibility, buildInput } from './fields.js';
import { renderGroupActions } from './groupActions.js';

export function renderGroups() {
  const host = $('#groups');
  // 重绘会丢掉折叠状态，先记下来再还原
  const collapsed = new Set($$('.group.collapsed', host).map(c => c.dataset.gid));
  host.innerHTML = '';

  state.schema.groups.forEach(g => {
    const card = el('div', 'group');
    card.dataset.gid = g.id;
    if (collapsed.has(g.id)) card.classList.add('collapsed');

    const head = el('div', 'group-head');
    head.append(
      el('span', 'group-title', g.title),
      el('span', 'group-badge', g.badge),
      el('span', 'group-arrow', '▼'),
    );
    head.addEventListener('click', () => card.classList.toggle('collapsed'));
    card.appendChild(head);

    const body = el('div', 'group-body');
    if (g.hint) body.appendChild(el('div', 'group-hint', g.hint));
    g.fields.forEach(f => body.appendChild(renderField(f, g)));
    body.appendChild(renderGroupActions(g));
    card.appendChild(body);

    host.appendChild(card);
  });

  applyConditionalVisibility();
}

function renderField(f, group) {
  const row = el('div', 'field');
  row.dataset.fieldkey = f.key;
  if (f.showIf) row.dataset.showif = JSON.stringify(f.showIf);

  const label = el('div', 'field-label');
  label.appendChild(el('div', 'field-name', f.label));
  label.appendChild(el('div', 'field-key', f.key));
  if (f.description) label.appendChild(el('div', 'field-desc', f.description));
  if (f.note) label.appendChild(el('div', 'field-note', '⚠ ' + f.note));
  row.appendChild(label);

  const wrap = el('div', 'field-input');
  wrap.appendChild(buildInput(f, group));
  row.appendChild(wrap);
  return row;
}
