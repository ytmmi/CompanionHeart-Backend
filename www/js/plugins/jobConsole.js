/* 任务控制台：安装 / 启动的流式日志。
 *
 * 后端把慢操作放进后台线程，只返回 job_id；这里按 since 增量轮询，
 * 拿到的行直接追加到 <pre> 里。任务结束（ok / error）就停止轮询。
 */

import { api } from '../core/api.js';
import { emit, EVT } from '../core/bus.js';
import { $, el } from '../core/dom.js';

export function openJobConsole(jobId, title, onDone) {
  const con = $('#jobConsole');
  const body = $('#jcBody');
  $('#jcTitle').textContent = title;
  $('#jcStatus').textContent = '进行中…';
  $('#jcStatus').className = 'jc-status running';
  $('#jcFoot').innerHTML = '';
  body.textContent = '';
  con.classList.remove('hidden');

  let since = 0;
  let stopped = false;

  const close = () => {
    stopped = true;
    con.classList.add('hidden');
  };
  $('#jcClose').onclick = close;

  const poll = async () => {
    if (stopped) return;
    try {
      const r = await api(`/api/plugins/job?id=${jobId}&since=${since}`);
      if (!r.ok) { $('#jcStatus').textContent = r.error || '任务丢失'; return; }
      if (r.lines.length) {
        since = r.next;
        body.textContent += r.lines.join('\n') + '\n';
        body.scrollTop = body.scrollHeight;
      }
      if (r.status === 'running') {
        setTimeout(poll, 700);
        return;
      }

      const ok = r.status === 'ok';
      $('#jcStatus').textContent = ok ? '✓ 完成' : '✕ 失败';
      $('#jcStatus').className = 'jc-status ' + (ok ? 'ok' : 'err');
      const btn = el('button', 'btn sm', '关闭');
      btn.addEventListener('click', close);
      $('#jcFoot').appendChild(btn);
      if (ok && onDone) onDone();
      else emit(EVT.PLUGINS_RELOAD);
    } catch (e) {
      $('#jcStatus').textContent = '轮询失败：' + e.message;
      $('#jcStatus').className = 'jc-status err';
    }
  };
  poll();
}
