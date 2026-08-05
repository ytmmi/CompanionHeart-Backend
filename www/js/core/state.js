/* 全局状态与 dirty 表。
 *
 * 简单视图与高级视图共用同一份 dirty（key -> 新值），所以两边切换时
 * 未保存的改动不会丢。dirty 只记「与磁盘不同」的项：改回原值会自动移除，
 * 避免用户来回拨一下就被当成有改动。
 */

import { emit, EVT } from './bus.js';

export const state = {
  schema: null,        // 简单视图分组
  keys: {},            // 高级视图：key -> {value, description}
  original: {},        // key -> 磁盘上的原值
  dirty: new Map(),    // key -> 新值
  view: 'simple',
  edgeVoices: null,    // 微软语音目录（懒加载）
  trashDir: '',        // 插件回收站路径
};

export const MODULE_FILES = {
  llm:   'app/configs/llm/config.yaml',
  tts:   'app/configs/tts/config.yaml',
  agent: 'app/configs/agent/config.yaml',
  asr:   'app/configs/asr/config.yaml',
};

/** 值是否与磁盘原值相同（按字符串比，规避 0.7 vs "0.7"） */
function sameAsOriginal(key, val) {
  const o = state.original[key];
  if (typeof o === 'boolean') return Boolean(val) === o;
  return String(val ?? '') === String(o ?? '');
}

export function setDirty(key, val) {
  if (sameAsOriginal(key, val)) state.dirty.delete(key);
  else state.dirty.set(key, val);
  emit(EVT.DIRTY_CHANGED);
}

export function clearDirty() {
  state.dirty.clear();
  emit(EVT.DIRTY_CHANGED);
}

/** 当前生效值：改过取 dirty，否则取磁盘值 */
export function currentValue(key) {
  return state.dirty.has(key) ? state.dirty.get(key) : state.original[key];
}

/** 用一次全量拉取的结果重置状态（dirty 由调用方决定是否先清） */
export function adoptSnapshot(schema, keys) {
  state.schema = schema;
  state.keys = keys;
  state.original = Object.fromEntries(
    Object.entries(keys).map(([k, m]) => [k, m.value]));
}
