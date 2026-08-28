<template>
  <div class="statusline" :class="{ warn: appState.degraded || appState.offline }" role="status" aria-live="polite">
    <span>{{ statusText }}</span><span v-if="appState.degraded" class="b-bad">服务异常</span>
    <button v-if="appState.degraded || appState.offline" class="status-retry" type="button" @click="refreshAll">重试</button>
  </div>
  <div v-if="hasErrors" class="error-banner" role="alert">
    <span>部分数据暂时不可用：</span><span v-if="appState.errors.jobs">任务</span><span v-if="appState.errors.overview">概览</span><span v-if="appState.errors.files">文件</span>
    <button type="button" class="status-retry" @click="refreshAll">重新同步</button>
  </div>
</template>
<script setup>
import { computed } from "vue";
import { appState } from "../../stores/appStore.js";
import { refreshAll } from "../../stores/syncStore.js";

const hasErrors = computed(() => Object.values(appState.errors).some(Boolean));
const statusText = computed(() => {
  if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
  if (appState.degraded) return "部分数据同步失败";
  return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
});
</script>
