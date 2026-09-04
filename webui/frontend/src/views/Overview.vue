<template>
  <div class="overview">
    <section class="hero" aria-label="实时状态">
      <div class="hero-live">
        <span class="rec-dot" :class="{ idle: !overviewState.running }" aria-hidden="true"></span>
        <div><div class="hero-num">{{ overviewState.running ?? "—" }}</div><div class="hero-cap">正在录制</div></div>
      </div>
      <div class="hero-meta">
        <span>任务 <b>{{ overviewState.jobs ?? "—" }}</b></span>
        <span>失败 <b>{{ overviewState.failed ?? "—" }}</b></span>
        <span>可用 <b>{{ fmtBytes(overviewState.disk_free) }}</b></span>
        <span>占用 <b>{{ overviewState.disk_percent ?? "—" }}%</b></span>
      </div>
      <div class="hero-actions">
        <button v-if="overviewState.failed" class="danger" type="button" @click="navigate('/tasks')">查看失败任务</button>
        <button class="secondary" type="button" @click="navigate('/new')">新建任务</button>
      </div>
    </section>
    <section class="stats">
      <MetricCard label="正在录制" icon="REC" :value="overviewState.running ?? '—'" note="个活动任务" />
      <MetricCard label="任务总数" icon="ALL" :value="overviewState.jobs ?? '—'" note="个托管任务" />
      <MetricCard label="可用空间" icon="SSD" :value="fmtBytes(overviewState.disk_free)" note="录制目录剩余" />
      <MetricCard label="磁盘占用" icon="%" :value="(overviewState.disk_percent ?? '—') + '%'" note="" :bar="diskPercent" />
    </section>
    <div class="sysinfo">
      <span>负载 <b>{{ load1 }}</b></span>
      <span>内存 <b>{{ memPercent }}</b></span>
      <span>更新于 <b>{{ updated }}</b></span>
      <span class="sync-status" :class="{ warn: appState.degraded }">{{ syncText }}</span>
    </div>

    <section v-if="platforms.length" class="panel" aria-label="平台任务统计">
      <div class="panel-title">
        <div class="title-wrap"><span class="section-icon" aria-hidden="true">▦</span><div><h2>平台分布</h2><span class="panel-kicker">各平台托管任务占比</span></div></div>
      </div>
      <div class="dist">
        <button v-for="[platform, count] in platforms" :key="platform" class="dist-row link-button" type="button" @click="showPlatform(platform)" :title="'查看' + (PLATFORM_ZH[platform] || platform) + '任务'">
          <span class="dist-name">{{ PLATFORM_ZH[platform] || platform }}</span>
          <span class="dist-track"><i class="dist-fill" :style="{ width: distWidth(count) + '%', background: LOGO_COLORS[platform] || undefined }"></i></span>
          <span class="dist-num">{{ count }}</span>
        </button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap"><span class="section-icon" aria-hidden="true">●</span><div><h2>最近任务</h2><span class="panel-kicker">点击查看日志与详情</span></div></div>
        <div class="filter-bar"><input v-model="taskState.query" placeholder="搜索频道或平台" aria-label="搜索最近任务"><button class="secondary" type="button" @click="navigate('/tasks')">全部任务</button></div>
      </div>
      <TaskList :jobs="recentJobs" :filtered="Boolean(taskState.query)" @open="openTask" @restart="askRestart" @stop="askStop" />
    </section>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap"><span class="section-icon" aria-hidden="true">□</span><div><h2>最近文件</h2><span class="panel-kicker">最近生成的媒体文件</span></div></div>
        <button class="secondary" type="button" @click="navigate('/library')">查看全部</button>
      </div>
      <FileBrowser :files="overviewState.files || []" :total="(overviewState.files || []).length" @delete="askDeleteRecording" />
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import MetricCard from "../features/dashboard/MetricCard.vue";
import TaskList from "../features/tasks/TaskList.vue";
import FileBrowser from "../features/recordings/FileBrowser.vue";
import { appState } from "../stores/appStore.js";
import { taskState } from "../stores/taskStore.js";
import { overviewState } from "../stores/overviewStore.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../config/platforms.js";
import { fmtBytes } from "../utils.js";
import { navigate } from "../router.js";
import { openTask, askStop, askRestart } from "../features/tasks/taskActions.js";
import { askDeleteRecording } from "../features/recordings/recordingActions.js";

const diskPercent = computed(() => Number(overviewState.disk_percent) || 0);
const load1 = computed(() => overviewState.load?.[0] != null ? overviewState.load[0].toFixed(2) : "—");
const memPercent = computed(() => overviewState.mem_total ? ((1 - overviewState.mem_available / overviewState.mem_total) * 100).toFixed(0) + "%" : "—");
const updated = computed(() => overviewState.server_time ? new Date(overviewState.server_time * 1000).toLocaleTimeString() : "—");
const platforms = computed(() => Object.entries(overviewState.platforms || {}).sort((a, b) => b[1] - a[1]));
const recentJobs = computed(() => {
  const query = taskState.query.trim().toLowerCase();
  return taskState.jobs.filter((job) => !query || (job.target + " " + job.platform + " " + job.unit).toLowerCase().includes(query)).slice(0, 6);
});
const syncText = computed(() => {
  if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
  if (appState.degraded) return "部分数据同步失败";
  return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
});
function showPlatform(platform) { taskState.platformFilter = platform; navigate("/tasks"); }
function distWidth(count) {
  const max = Math.max(1, ...platforms.value.map(([, n]) => n));
  return Math.max(6, Math.round((count / max) * 100));
}
</script>
