<template>
  <div class="filter-bar">
    <input v-model="taskState.query" placeholder="搜索频道或平台" aria-label="搜索任务">
    <select v-model="taskState.stateFilter" aria-label="状态筛选">
      <option value="all">全部状态</option>
      <option value="active">运行中</option>
      <option value="failed">失败</option>
      <option value="inactive">已停止</option>
    </select>
    <select v-model="taskState.platformFilter" aria-label="平台筛选">
      <option value="all">全部平台</option>
      <option v-for="platform in platforms" :key="platform" :value="platform">{{ PLATFORM_ZH[platform] || platform }}</option>
    </select>
    <button class="secondary" type="button" :disabled="busy" @click="$emit('refresh')">{{ busy ? "同步中…" : "刷新" }}</button>
    <button v-if="hasFilter" class="text-button" type="button" @click="clearFilters">清除筛选</button>
  </div>
</template>
<script setup>
import { computed } from "vue";
import { taskState } from "../../stores/taskStore.js";
import { PLATFORM_ZH } from "../../config/platforms.js";

defineProps({ platforms: { type: Array, default: () => [] }, busy: Boolean });
defineEmits(["refresh"]);
const hasFilter = computed(() => Boolean(taskState.query.trim() || taskState.stateFilter !== "all" || taskState.platformFilter !== "all"));
function clearFilters() {
  taskState.query = "";
  taskState.stateFilter = "all";
  taskState.platformFilter = "all";
}
</script>
