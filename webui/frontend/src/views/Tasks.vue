<template>
  <div class="tasks">
    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
          <div><h2>录制任务<span class="count">{{ countText }}</span></h2><span class="panel-kicker">实时状态与进程控制</span></div>
        </div>
        <TaskFilters :platforms="platformNames" :busy="appState.busy" @refresh="refreshAll({ includeFiles: false })" />
      </div>
      <div v-if="platforms.length" id="chips" aria-label="平台任务统计">
        <button v-for="[platform, count] in platforms" :key="platform" class="chip" type="button" @click="taskState.platformFilter = platform">
          {{ PLATFORM_ZH[platform] || platform }} <b :style="{ color: LOGO_COLORS[platform] || 'var(--blue)' }">{{ count }}</b>
        </button>
      </div>
      <TaskList :jobs="filteredJobs" :filtered="hasFilter" @open="openTask" @restart="askRestart" @stop="askStop" />
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import TaskFilters from "../features/tasks/TaskFilters.vue";
import TaskList from "../features/tasks/TaskList.vue";
import { taskState } from "../stores/taskStore.js";
import { appState } from "../stores/appStore.js";
import { overviewState } from "../stores/overviewStore.js";
import { refreshAll } from "../stores/syncStore.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../config/platforms.js";
import { openTask, askStop, askRestart } from "../features/tasks/taskActions.js";

const platforms = computed(() => Object.entries(overviewState.platforms || {}).sort((a, b) => b[1] - a[1]));
const platformNames = computed(() => Object.keys(overviewState.platforms || {}).sort());
const hasFilter = computed(() => Boolean(taskState.query.trim() || taskState.stateFilter !== "all" || taskState.platformFilter !== "all"));
const filteredJobs = computed(() => taskState.jobs.filter((job) => {
  if (taskState.stateFilter !== "all" && job.state !== taskState.stateFilter) return false;
  if (taskState.platformFilter !== "all" && job.platform !== taskState.platformFilter) return false;
  const query = taskState.query.trim().toLowerCase();
  return !query || (job.target + " " + job.platform + " " + job.unit).toLowerCase().includes(query);
}));
const countText = computed(() => taskState.jobs.length ? `${filteredJobs.value.length}/${taskState.jobs.length} 个` : "无任务");
</script>
