/* 插件安装面板（从 Git / 从本地目录）。
 *
 * 安装会对第三方代码执行 pip install，等同运行未审计的代码，
 * 所以必须先勾选风险确认，按钮才解锁。
 */

import { postJSON } from '../core/api.js';
import { emit, EVT } from '../core/bus.js';
import { $, $$ } from '../core/dom.js';
import { toast } from '../core/toast.js';
import { openJobConsole } from './jobConsole.js';

export function initInstallPanel() {
  $$('.it-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.it-btn').forEach(b => b.classList.toggle('active', b === btn));
      const src = btn.dataset.src;
      $('#formGit').classList.toggle('hidden', src !== 'git');
      $('#formLocal').classList.toggle('hidden', src !== 'local');
    });
  });

  $('#riskAck').addEventListener('change', e => {
    $('#installBtn').disabled = !e.target.checked;
  });

  $('#installBtn').addEventListener('click', doInstall);
}

async function doInstall() {
  const src = $('.it-btn.active').dataset.src;
  const body = { source: src };
  let title;

  if (src === 'git') {
    body.url = $('#gitUrl').value.trim();
    body.branch = $('#gitBranch').value.trim() || 'main';
    body.name = $('#gitName').value.trim();
    if (!body.url) { toast('请填写 Git 地址', 'warn'); return; }
    title = `安装 ${body.name || body.url}`;
  } else {
    body.path = $('#localPath').value.trim();
    if (!body.path) { toast('请填写本地路径', 'warn'); return; }
    title = `安装 ${body.path}`;
  }

  try {
    const r = await postJSON('/api/plugins/install', body);
    if (!r.ok) throw new Error(r.error);
    openJobConsole(r.job, title, resetInstallForm);
  } catch (e) {
    toast('安装失败：' + e.message, 'error', 5200);
  }
}

/** 安装成功后清空表单、重置风险勾选、刷新列表 */
function resetInstallForm() {
  $('#gitUrl').value = ''; $('#gitName').value = '';
  $('#localPath').value = '';
  $('#riskAck').checked = false; $('#installBtn').disabled = true;
  emit(EVT.PLUGINS_RELOAD);
}
