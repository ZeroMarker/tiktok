<template>
  <div class="tasks">
    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
          <div>
            <h2>录制任务<span class="count">{{ countText }}</span></h2>
            <span class="panel-kicker">实时状态与进程控制</span>
          </div>
        </div>
        <div class="filter-bar">
          <input v-model="state.jobQuery" placeholder="搜索频道…" aria-label="搜索任务">
          <select v-model="state.stateFilter" aria-label="状态筛选">
            <option value="all">全部状态</option>
            <option value="active">运行中</option>
            <option value="failed">失败</option>
            <option value="inactive">已停止</option>
          </select>
          <button class="secondary" @click="refreshAll">刷新</button>
        </div>
      </div>
      <div v-if="platforms.length" id="chips">
        <span v-for="[p, n] in platforms" :key="p" class="chip">
          {{ PLATFORM_ZH[p] || p }}
          <b :style="{ color: LOGO_COLORS[p] || 'var(--blue)' }">{{ n }}</b>
        </span>
      </div>
      <div class="jobs">
        <JobCard
          v-for="j in filteredJobs"
          :key="j.unit"
          :job="j"
          :selected="j.unit === state.selectedUnit"
          @open="openJob"
          @restart="askRestart"
          @stop="askStop"
        />
        <div v-if="!filteredJobs.length" class="empty">当前没有录制任务</div>
      </div>
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import JobCard from "../components/JobCard.vue";
import { state, refreshAll } from "../store.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../utils.js";
import { openJob, askStop, askRestart } from "../actions.js";

const platforms = computed(() =>
  Object.entries(state.overview.platforms || {}).sort((a, b) => b[1] - a[1])
);
const filteredJobs = computed(() => {
  const q = state.jobQuery.trim().toLowerCase();
  return state.jobs.filter((j) => {
    if (state.stateFilter !== "all" && j.state !== state.stateFilter) return false;
    if (!q) return true;
    return (j.target + " " + j.platform + " " + j.unit).toLowerCase().includes(q);
  });
});
const countText = computed(() =>
  state.jobs.length ? `${filteredJobs.length}/${state.jobs.length} 个` : "无任务"
);
</script>
