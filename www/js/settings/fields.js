/* 简单视图的字段控件。
 *
 * schema 里每个 field 的 type 决定渲染成哪种控件，各分支只管建 DOM 与
 * 在值变化时 commit 到 dirty 表。需要联网的三种（port / model / edgevoice）
 * 都是点了才发请求，进页面时不打扰后端。
 */

import { api } from '../core/api.js';
import { $$, el } from '../core/dom.js';
import { currentValue, setDirty, state } from '../core/state.js';
import { toast } from '../core/toast.js';

export function buildInput(f, group) {
  const box = el('div');
  const commit = v => setDirty(f.key, v);
  const val = currentValue(f.key);

  switch (f.type) {
    case 'switch':    buildSwitch(box, val, commit); break;
    case 'select':    buildSelect(box, f, val, commit); break;
    case 'password':  buildPassword(box, f, val, commit); break;
    case 'textarea':  buildTextarea(box, f, val, commit); break;
    case 'number':    buildNumber(box, f, val, commit); break;
    case 'slider':    buildSlider(box, f, val, commit); break;
    case 'port':      buildPort(box, f, val, commit, group); break;
    case 'model':     buildModel(box, f, val, commit); break;
    case 'edgevoice': buildEdgeVoice(box, f, val, commit); break;
    default:          buildText(box, f, val, commit);
  }

  return box;
}

// ── 基础控件 ──

function buildSwitch(box, val, commit) {
  const sw = el('label', 'switch');
  const cb = el('input');
  cb.type = 'checkbox';
  cb.checked = Boolean(val);
  cb.addEventListener('change', () => commit(cb.checked));
  sw.append(cb, el('span', 'track'));
  box.appendChild(sw);
}

function buildSelect(box, f, val, commit) {
  const sel = el('select');
  (f.options || []).forEach(o => {
    const opt = el('option', null, o.label);
    opt.value = o.value;
    sel.appendChild(opt);
  });
  sel.value = val ?? '';
  sel.addEventListener('change', () => {
    commit(sel.value);
    applyConditionalVisibility();
    if (f.emotions !== undefined) refreshEmotions(box, sel.value);
  });
  box.appendChild(sel);

  // 角色情感标签（仅 TTS 插件角色，供试听选情感）
  if (f.emotions !== undefined) {
    const holder = el('div', 'emotions');
    holder.dataset.role = 'emotions';
    box.appendChild(holder);
    refreshEmotions(box, sel.value);
  }
}

function buildPassword(box, f, val, commit) {
  const rowEl = el('div', 'pw-row');
  const inp = el('input');
  inp.type = 'password';
  inp.value = val ?? '';
  inp.placeholder = f.placeholder || '';
  inp.addEventListener('input', () => commit(inp.value));
  rowEl.append(inp, makeEyeButton(inp));
  box.appendChild(rowEl);
}

/** 密码框的显示 / 隐藏切换按钮（简单视图与高级视图共用） */
export function makeEyeButton(inp) {
  const eye = el('button', 'btn sm', '显示');
  eye.type = 'button';
  eye.addEventListener('click', () => {
    const hidden = inp.type === 'password';
    inp.type = hidden ? 'text' : 'password';
    eye.textContent = hidden ? '隐藏' : '显示';
  });
  return eye;
}

function buildTextarea(box, f, val, commit) {
  const ta = el('textarea');
  ta.rows = f.rows || 5;
  ta.value = val ?? '';
  ta.placeholder = f.placeholder || '';
  ta.addEventListener('input', () => commit(ta.value));
  box.appendChild(ta);
}

function buildNumber(box, f, val, commit) {
  const inp = el('input');
  inp.type = 'number';
  if (f.min != null) inp.min = f.min;
  if (f.max != null) inp.max = f.max;
  if (f.step != null) inp.step = f.step;
  inp.value = val ?? '';
  inp.addEventListener('input', () => commit(inp.value));
  box.appendChild(inp);
}

function buildSlider(box, f, val, commit) {
  const rowEl = el('div', 'slider-row');
  const rng = el('input');
  rng.type = 'range';
  rng.min = f.min ?? 0;
  rng.max = f.max ?? 1;
  rng.step = f.step ?? 0.01;
  rng.value = val ?? 0;
  const out = el('span', 'slider-val', String(val ?? ''));
  rng.addEventListener('input', () => {
    out.textContent = rng.value;
    commit(rng.value);
  });
  rowEl.append(rng, out);
  box.appendChild(rowEl);
}

function buildText(box, f, val, commit) {
  const inp = el('input');
  inp.type = 'text';
  inp.value = val ?? '';
  inp.placeholder = f.placeholder || '';
  inp.addEventListener('input', () => commit(inp.value));
  box.appendChild(inp);

  if (f.presets) {
    const chips = el('div', 'presets');
    f.presets.forEach(p => {
      const c = el('span', 'preset-chip', p.label);
      c.title = p.value;
      c.addEventListener('click', () => {
        inp.value = p.value;
        commit(p.value);
      });
      chips.appendChild(c);
    });
    box.appendChild(chips);
  }
}

// ── 需要联网的控件 ──

function buildPort(box, f, val, commit, group) {
  const inp = el('input');
  inp.type = 'number';
  inp.min = f.min ?? 1024;
  inp.max = f.max ?? 65535;
  inp.value = val ?? '';
  const msg = el('div', 'port-msg');
  let timer;

  const check = async () => {
    const p = parseInt(inp.value, 10);
    if (!p) { msg.textContent = ''; return; }
    try {
      const r = await api(`/api/settings/check-port?port=${p}&module=${group.id}`);
      msg.className = `port-msg ${r.level}`;
      msg.textContent = r.issues.length
        ? r.issues.join('；')
        : `端口 ${p} 可用，符合 ${group.badge} 约定端口段`;
    } catch { msg.textContent = ''; }
  };

  inp.addEventListener('input', () => {
    commit(inp.value);
    clearTimeout(timer);
    timer = setTimeout(check, 380);
  });
  box.append(inp, msg);
  check();
}

function buildModel(box, f, val, commit) {
  const rowEl = el('div', 'combo');
  const listId = `dl-${f.key.replace(/\./g, '-')}`;
  const inp = el('input');
  inp.type = 'text';
  inp.value = val ?? '';
  inp.setAttribute('list', listId);
  inp.addEventListener('input', () => commit(inp.value));

  const dl = el('datalist');
  dl.id = listId;

  const btn = el('button', 'btn sm', '拉取列表');
  btn.type = 'button';
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '拉取中…';
    try {
      const r = await api(`/api/settings/llm-models?mode=${f.modelSource}`);
      if (r.ok && r.models.length) {
        dl.innerHTML = '';
        r.models.forEach(m => {
          const o = el('option');
          o.value = m;
          dl.appendChild(o);
        });
        toast(`拉到 ${r.models.length} 个模型，点输入框可选`, 'success');
        inp.focus();
      } else {
        toast(`拉取失败：${r.error || '无模型'}${r.hint ? '。' + r.hint : ''}`, 'warn', 5200);
      }
    } catch (e) {
      toast(`拉取失败：${e.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '拉取列表';
    }
  });

  rowEl.append(inp, btn);
  box.append(rowEl, dl);
}

function buildEdgeVoice(box, f, val, commit) {
  const rowEl = el('div', 'combo');
  const sel = el('select');
  const cur = el('option', null, val || '（未设置）');
  cur.value = val ?? '';
  sel.appendChild(cur);
  sel.addEventListener('change', () => commit(sel.value));

  const btn = el('button', 'btn sm', '加载语音库');
  btn.type = 'button';
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '加载中…';
    try {
      if (!state.edgeVoices) {
        const r = await api('/api/settings/edge-voices');
        state.edgeVoices = r.voices;
      }
      fillEdgeVoices(sel, currentValue(f.key));
      toast(`已加载 ${state.edgeVoices.length} 个微软语音`, 'success');
    } catch (e) {
      toast(`加载失败：${e.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '重新加载';
    }
  });

  rowEl.append(sel, btn);
  box.appendChild(rowEl);
}

function fillEdgeVoices(sel, current) {
  sel.innerHTML = '';
  const byLocale = {};
  state.edgeVoices.forEach(v => (byLocale[v.locale] ||= []).push(v));

  // 中日英排前面 —— 这是项目实际用到的三种语言
  const priority = ['zh-CN', 'zh-TW', 'zh-HK', 'ja-JP', 'en-US', 'en-GB'];
  const locales = [
    ...priority.filter(l => byLocale[l]),
    ...Object.keys(byLocale).sort().filter(l => !priority.includes(l)),
  ];

  locales.forEach(loc => {
    const g = el('optgroup');
    g.label = loc;
    byLocale[loc].forEach(v => {
      const tail = v.personalities?.length ? ' · ' + v.personalities.slice(0, 2).join('/') : '';
      const o = el('option', null,
        `${v.voice} — ${v.gender === 'Female' ? '女' : '男'}${tail}`);
      o.value = v.voice;
      g.appendChild(o);
    });
    sel.appendChild(g);
  });
  sel.value = current ?? '';
}

// ── 情感标签与条件显示 ──

function refreshEmotions(box, charName) {
  const holder = box.querySelector('[data-role="emotions"]');
  if (!holder) return;
  const hit = (state.schema?._characters || []).find(c => c.voice === charName);
  const list = hit?.emotions || [];
  holder.innerHTML = '';
  if (!list.length) return;

  holder.appendChild(el('span', 'lbl', '试听情感：'));
  list.forEach((emo, i) => {
    const chip = el('span', `emo-chip${i === 0 ? ' active' : ''}`, emo);
    chip.dataset.emo = emo;
    chip.addEventListener('click', () => {
      $$('.emo-chip', holder).forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    });
    holder.appendChild(chip);
  });
}

/** 按 showIf 条件显示/隐藏字段（如切 tts.mode 时整组字段换掉） */
export function applyConditionalVisibility() {
  $$('[data-showif]').forEach(row => {
    const cond = JSON.parse(row.dataset.showif);
    const actual = String(currentValue(cond.key) ?? '');
    row.classList.toggle('hidden', actual !== String(cond.equals));
  });
}
