<template>
  <main class="shell">
    <header>
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"></div>
        <div>
          <p class="eyebrow">Live Control</p>
          <h1>直播录制中心</h1>
          <p class="sub">聚合管理跨平台录制任务</p>
        </div>
      </div>
      <div class="head-right">
        <div class="status-pill">
          <div class="online"><i class="dot"></i><span>{{ connText }}</span></div>
        </div>
        <div class="clock-pill"><span>{{ clock }}</span></div>
        <button v-if="installable" id="install-btn" class="secondary install" @click="install">安装应用</button>
      </div>
    </header>

    <nav class="nav" aria-label="主导航">
      <button
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: isActive(item) }"
        @click="navigate(item.path)"
      >
        {{ item.label }}
      </button>
    </nav>

    <div class="statusline" :class="{ warn: state.degraded || state.offline }">
      <span>{{ statusText }}</span>
      <span v-if="state.degraded" class="b-bad">服务异常</span>
    </div>

    <component :is="viewComponent" :key="viewKey" :unit="route.unit" />

    <PlayerModal />
    <div id="modal" class="modal" :class="{ hidden: !ui.confirm.visible }" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-text">
      <div class="modal-box">
        <h3 id="modal-title">{{ ui.confirm.title }}</h3>
        <p id="modal-text">{{ ui.confirm.text }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="closeConfirm">取消</button>
          <button :class="ui.confirm.danger ? 'danger' : 'secondary'" @click="ok">{{ ui.confirm.okText }}</button>
        </div>
      </div>
    </div>
    <div id="toast" class="toast" v-show="ui.toast" role="status" aria-live="polite">{{ ui.toast }}</div>
  </main>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import Overview from "./views/Overview.vue";
import Tasks from "./views/Tasks.vue";
import TaskDetail from "./views/TaskDetail.vue";
import Library from "./views/Library.vue";
import NewTask from "./views/NewTask.vue";
import PlayerModal from "./components/PlayerModal.vue";
import { state } from "./store.js";
import { route, navigate } from "./router.js";
import { ui, closeConfirm } from "./ui.js";

const views = { overview: Overview, tasks: Tasks, task: TaskDetail, library: Library, new: NewTask };
const viewComponent = computed(() => views[route.value.name] || Overview);
const viewKey = computed(() => route.value.name + (route.value.unit || ""));

const navItems = [
  { path: "/", label: "概览", name: "overview" },
  { path: "/tasks", label: "任务", name: "tasks" },
  { path: "/library", label: "文件库", name: "library" },
  { path: "/new", label: "新建", name: "new" },
];
function isActive(item) {
  return route.value.name === item.name || (item.name === "tasks" && route.value.name === "task");
}

const clock = ref("");
let clockTimer = null;
onMounted(() => {
  clock.value = new Date().toLocaleTimeString();
  clockTimer = setInterval(() => (clock.value = new Date().toLocaleTimeString()), 1000);
});
onUnmounted(() => clearInterval(clockTimer));

const connText = computed(() => (state.offline ? "离线" : state.degraded ? "服务异常" : "服务在线"));
const statusText = computed(() => {
  if (state.offline) return state.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
  if (state.degraded) return "同步失败";
  return state.lastSynced ? "已同步 " + new Date(state.lastSynced).toLocaleTimeString() : "等待同步";
});

const installable = computed(() => !!state.installPrompt);
async function install() {
  if (!state.installPrompt) return;
  state.installPrompt.prompt();
  await state.installPrompt.userChoice;
  state.installPrompt = null;
}
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  state.installPrompt = e;
});

function ok() {
  const cb = ui.confirm.cb;
  closeConfirm();
  if (cb) cb();
}
</script>
<style scoped>
.nav {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  margin: 0 0 12px;
}
.nav-item {
  min-height: 36px;
  padding: 7px 14px;
  font-size: 12px;
  border-radius: 999px;
  background: #0b1615;
  border: 1px solid var(--line);
  color: var(--muted);
  cursor: pointer;
}
.nav-item:hover {
  border-color: var(--line-strong);
  color: var(--text);
}
.nav-item.active {
  background: rgba(88, 224, 173, 0.14);
  border-color: rgba(88, 224, 173, 0.5);
  color: var(--brand);
}
.statusline {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 11px;
  margin: 0 2px 8px;
}
.statusline.warn {
  color: var(--warn);
}
@media (max-width: 680px) {
  .nav-item {
    flex: 1;
    text-align: center;
  }
}
</style>
