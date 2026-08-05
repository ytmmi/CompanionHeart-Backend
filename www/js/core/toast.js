/* 轻提示 */

import { $, el } from './dom.js';

export function toast(msg, kind = 'info', ms = 3600) {
  const t = el('div', `toast ${kind}`, msg);
  $('#toastHost').appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity .3s';
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 320);
  }, ms);
}
