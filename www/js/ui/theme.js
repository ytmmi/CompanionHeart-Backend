/* 深色 / 浅色主题 */

import { $ } from '../core/dom.js';

export function initTheme() {
  const saved = localStorage.getItem('ch-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));

  $('#themeBtn').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('ch-theme', next);
  });

  // 用户没手动选过时跟随系统
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    if (!localStorage.getItem('ch-theme')) applyTheme(e.matches ? 'dark' : 'light');
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('#themeBtn').textContent = theme === 'dark' ? '☀' : '◐';
}
