<template>
  <div class="overview">
    <section class="stats">
      <StatCard label="正在录制" icon="REC" :value="state.overview.running ?? '—'" note="个活动任务" />
      <StatCard label="任务总览" icon="ALL" :value="state.overview.jobs ?? '—'" note="个托管任务" />
      <StatCard label="可用空间" icon="SSD" :value="fmtBytes(state.overview.disk_free)" note="录制目录剩余" />
      <StatCard
        label="磁盘占用"
        icon="%"
        :value="(state.overview.disk_percent ?? '—') + '%'"
        note=""
        :bar="diskPercent"
      />
    </section>

    <div class="sysinfo">
      <span>负载 <b>{{ load1 }}</b></span>
      <span>内存 <b>{{ memPercent }}</b></span>
      <span>更新于 <b>{{ updated }}</b></span>
      <span class="sync-status" :class="{ warn: state.degraded }">{{ syncText }}</span>
    </div>

    <div v-if="platforms.length" id="chips">
      <span v-for="[p, n] in platforms" :key="p" class="chip">
        {{ PLATFORM_ZH[p] || p }}
        <b :style="{ color: LOGO_COLORS[p] || 'var(--blue)' }">{{ n }}</b>
      </span>
    </div>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">＋</span>
          <div><h2>新建录制</h2><span class="panel-kicker">选择平台并输入直播间信息</span></div>
        </div>
        <button class="secondary" @click="navigate('/new')">进入新建</button>
      </div>
      <div class="hint">输入 TikTok 用户名或完整直播地址。</div>
    </section>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
          <div><h2>最近任务</h2><span class="panel-kicker">点击查看日志与详情报</span></div>
        </div>
        <div class="filter-bar">
          <input v-model="state.jobQuery" placeholder="搜索频道…" aria-label="搜索任务">
          <button class="secondary" @click="navigate('/tasks')">全部任务</button>
        </div>
      </div>
      <div class="jobs">
        <JobCard
          v-for="j in recentJobs"
          :key="j.unit"
          :job="j"
          :selected="j.unit === state.selectedUnit"
          @open="openJob"
          @restart="askRestart"
          @stop="askStop"
        />
        <div v-if="!recentJobs.length" class="empty">当前没有录制任务</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">□</span>
          <div>
            <h2>最近文件</h2>
            <span class="panel-kicker">最近生成的媒体文件</span>
          </div>
        </div>
        <button class="secondary" @click="navigate('/library')">文件库</button>
      </div>
      <FileList :files="recentFiles" @delete="askDeleteFile" />
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import StatCard from "../components/StatCard.vue";
import JobCard from "../components/JobCard.vue";
import FileList from "../components/FileList.vue";
import { state } from "../store.js";
import { navigate } from "../router.js";
import { PLATFORM_ZH, LOGO_COLORS, fmtBytes } from "../utils.js";
import { openJob, askStop, askRestart, askDeleteFile } from "../actions.js";

const diskPercent = computed(() => Number(state.overview.disk_percent) || 0);
const load1 = computed(() => (state.overview.load && state.overview.load[0] != null ? state.overview.load[0].toFixed(2) : "—"));
const memPercent = computed(() =>
  state.overview.mem_total ? ((1 - state.overview.mem_available / state.overview.mem_total) * 100).toFixed(0) + "%" : "—"
);
const updated = computed(() =>
  state.overview.server_time ? new Date(state.overview.server_time * 1000).toLocaleTimeString() : "—"
);
const platforms = computed(() =>
  Object.entries(state.overview.platforms || {}).sort((a, b) => b[1] - a[1])
);
const syncText = computed(() => {
  if (state.offline) return state.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
  if (state.degraded) return "服务异常";
  return state.lastSynced ? "已同步 " + new Date(state.lastSynced).toLocaleTimeString() : "等待同步";
});
const recentJobs = computed(() => {
  const q = state.jobQuery.trim().toLowerCase();
  let list = state.jobs;
  if (q) list = list.filter((j) => (j.target + " " + j.platform + " " + j.unit).toLowerCase().includes(q));
  return list.slice(0, 6);
});
const recentFiles = computed(() => state.files.slice(0, 8));
</script>
