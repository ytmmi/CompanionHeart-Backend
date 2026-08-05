/* 设置服务 API 封装。
 *
 * 后端出错时也返回 JSON（带 error 字段），所以这里统一把 error 抛成异常，
 * 调用方只需 try/catch 一处。返回非 JSON 说明请求打到了静态文件或代理上。
 */

export async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const ct = r.headers.get('Content-Type') || '';
  if (!ct.includes('application/json')) throw new Error(`意外响应 (HTTP ${r.status})`);
  const data = await r.json();
  if (!r.ok && data.error) throw new Error(data.error);
  return data;
}

export const postJSON = (path, body) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
