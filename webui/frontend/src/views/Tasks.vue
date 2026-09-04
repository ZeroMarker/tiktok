<template>
  <div class="tasks">
    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon"><AppIcon name="tasks" /></span>
          <div><h2>录制任务<span class="count">{{ countText }}</span></h2><span class="panel-kicker">实时状态与进程控制</span></div>
        </div>
        <TaskFilters :platforms="platformNames" :busy="appState.busy" @refresh="refreshAll({ includeFiles: false })" />
      </div>
      <div v-if="platforms.length" id="chips" aria-label="平台任务统计">
        <button v-for="[platform, count] in platforms" :key="platform" class="chip" :class="{ on: taskState.platformFilter === platform }" type="button" :aria-pressed="taskState.platformFilter === platform" @click="taskState.platformFilter = platform">
          {{ PLATFORM_ZH[platform] || platform }} <b :style="{ color: LOGO_COLORS[platform] || 'var(--blue)' }">{{ count }}</b>
        </button>
      </div>
      <div v-if="!filteredJobs.length" class="empty">
        <strong>{{ hasFilter ? "没有符合条件的任务" : "还没有录制任务" }}</strong>
        <span>{{ hasFilter ? "请调整搜索关键词或筛选条件" : "创建一个任务后，它会显示在这里" }}</span>
        <button v-if="!hasFilter" class="secondary" type="button" @click="navigate('/new')">新建任务</button>
      </div>
      <div v-for="group in groups" :key="group.key" class="task-group">
        <h3 class="task-group-title"><span class="gdot" :style="{ color: group.color }" aria-hidden="true"></span>{{ group.title }}<span class="count">{{ group.jobs.length }}</span></h3>
        <TaskList :jobs="group.jobs" :filtered="true" @open="openTask" @restart="askRestart" @stop="askStop" />
      </div>
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import AppIcon from "../features/app/AppIcon.vue";
import TaskFilters from "../features/tasks/TaskFilters.vue";
import TaskList from "../features/tasks/TaskList.vue";
import { taskState } from "../stores/taskStore.js";
import { appState } from "../stores/appStore.js";
import { overviewState } from "../stores/overviewStore.js";
import { refreshAll } from "../stores/syncStore.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../config/platforms.js";
import { navigate } from "../router.js";

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
const groups = computed(() => {
  const running = [];
  const failed = [];
  const other = [];
  for (const job of filteredJobs.value) {
    if (job.state === "active") running.push(job);
    else if (job.state === "failed") failed.push(job);
    else other.push(job);
  }
  const byTarget = (a, b) => String(a.target || "").localeCompare(String(b.target || ""));
  running.sort(byTarget);
  failed.sort(byTarget);
  other.sort(byTarget);
  return [
    { key: "running", title: "运行中", color: "var(--brand)", jobs: running },
    { key: "failed", title: "已失败", color: "var(--red)", jobs: failed },
    { key: "other", title: "已停止", color: "var(--muted)", jobs: other },
  ].filter((group) => group.jobs.length);
});
</script>
