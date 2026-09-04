<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true"></div>
      <div><p class="eyebrow">Live Control</p><h1>直播录制中心</h1><p class="sub">聚合管理跨平台录制任务</p></div>
    </div>
    <div class="head-right">
      <div class="status-pill" :title="statusText"><div class="online"><i class="dot" aria-hidden="true"></i><span>{{ connectionText }}</span></div></div>
      <div class="clock-pill" :title="`本地时间 ${clock}`"><span>{{ clock }}</span></div>
      <button v-if="appState.installPrompt" class="secondary install" type="button" @click="install">安装应用</button>
      <button class="secondary refresh" type="button" :disabled="appState.busy" :aria-busy="appState.busy" @click="refreshAll">{{ appState.busy ? "同步中…" : "刷新" }}</button>
    </div>
  </header>
</template>
<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { appState } from "../../stores/appStore.js";
import { refreshAll } from "../../stores/syncStore.js";

const clock = ref("");
let clockTimer = null;
const connectionText = computed(() => appState.offline ? "离线" : appState.degraded ? "服务异常" : "服务在线");
const statusText = computed(() => {
  if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
  if (appState.degraded) return "部分数据同步失败";
  return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
});
function captureInstallPrompt(event) {
  event.preventDefault();
  appState.installPrompt = event;
}
onMounted(() => {
  clock.value = new Date().toLocaleTimeString();
  clockTimer = setInterval(() => { clock.value = new Date().toLocaleTimeString(); }, 1000);
  window.addEventListener("beforeinstallprompt", captureInstallPrompt);
});
onUnmounted(() => {
  clearInterval(clockTimer);
  window.removeEventListener("beforeinstallprompt", captureInstallPrompt);
});
async function install() {
  if (!appState.installPrompt) return;
  appState.installPrompt.prompt();
  await appState.installPrompt.userChoice;
  appState.installPrompt = null;
}
</script>
