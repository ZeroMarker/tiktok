// store.js — 极简响应式 store：写入即（合并到微任务后）通知订阅者。
//
// 为什么不是直接改对象：原实现用 vue reactive()，各处都是 `state.x = y` 直接赋值。
// 这里用深层 Proxy 保留同样的调用方式——读出嵌套对象时自动包一层，写入任意层级
// 都会触发通知；同一微任务内的多次写入合并为一次，避免 Object.assign 逐字段刷新。

const listeners = new Set();
let pending = false;

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function flush() {
  pending = false;
  for (const listener of [...listeners]) listener();
}

export function notifySoon() {
  if (pending) return;
  pending = true;
  queueMicrotask(flush);
}

const proxyCache = new WeakMap();

function isWrappable(value) {
  if (value === null || typeof value !== "object") return false;
  if (Array.isArray(value)) return true;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function wrap(value) {
  if (!isWrappable(value)) return value; // 含 Event、Date、DOM 节点等宿主对象
  const cached = proxyCache.get(value);
  if (cached) return cached;
  const proxy = new Proxy(value, {
    get(target, key, receiver) {
      return wrap(Reflect.get(target, key, receiver));
    },
    set(target, key, value2) {
      const previous = target[key];
      const result = Reflect.set(target, key, value2);
      if (!Object.is(previous, value2)) notifySoon();
      return result;
    },
    deleteProperty(target, key) {
      const had = key in target;
      const result = Reflect.deleteProperty(target, key);
      if (had) notifySoon();
      return result;
    },
  });
  proxyCache.set(value, proxy);
  return proxy;
}

/** 把一个普通对象/数组变成响应式 store（自身即 Proxy，直接读写即可）。 */
export function createStore(initial) {
  return wrap(initial);
}
