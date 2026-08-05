/* 极简事件总线。
 *
 * 拆模块后有几处天然的环：保存 → 重新加载 → 重绘分组 → 分组里的备份按钮
 * → 恢复后又要重新加载。用总线把这些「谁通知谁」的边收敛到一处，
 * 模块之间只依赖事件名，不互相 import，依赖图保持无环。
 */

const handlers = new Map();

export function on(event, fn) {
  if (!handlers.has(event)) handlers.set(event, []);
  handlers.get(event).push(fn);
}

/** 同步派发，返回各处理器的返回值（可能是 Promise） */
export function emit(event, ...args) {
  return (handlers.get(event) || []).map(fn => fn(...args));
}

/** 等所有处理器（含异步的）跑完 */
export function emitAsync(event, ...args) {
  return Promise.all(emit(event, ...args));
}

// ── 事件名常量，避免各处手写字符串拼错 ──
export const EVT = {
  DIRTY_CHANGED:  'dirty:changed',   // 未保存改动数量变了
  CONFIG_RELOAD:  'config:reload',   // 重新从磁盘拉配置并重绘（异步）
  RERENDER:       'views:rerender',  // 用现有 state 重绘两个视图，不碰磁盘
  STATUS_REFRESH: 'status:refresh',  // 刷新顶部服务状态灯
  PLUGINS_RELOAD: 'plugins:reload',  // 重新拉插件列表
  RESTART_HINT:   'restart:hint',    // 提示需要重启后端才能全部生效
};
