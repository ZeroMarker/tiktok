<template>
  <div class="task-detail">
    <section v-if="!job" class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon"><AppIcon name="tasks" /></span>
          <div><h2>任务详情</h2><span class="panel-kicker">{{ unit }}</span></div>
        </div>
        <div class="actions">
          <button class="secondary" type="button" @click="navigate('/tasks')">返回任务</button>
        </div>
      </div>
      <div class="hint warn">该任务当前不在 systemd 单元列表中（可能已移除），仍可查看最近日志。</div>
    </section>
    <div class="split">
      <section v-if="job" class="panel">
        <div class="panel-title">
          <div class="title-wrap">
            <span class="section-icon"><AppIcon name="tasks" /></span>
            <div>
              <h2>{{ job.target }}<span class="platform-tag">{{ PLATFORM_ZH[job.platform] || job.platform }}</span></h2>
              <span class="panel-kicker">{{ stateLabel(job.state, job.substate) }}</span>
            </div>
          </div>
        </div>
        <dl class="kv">
          <dt>状态</dt><dd>{{ stateLabel(job.state, job.substate) }}</dd>
          <dt>直播</dt><dd :class="liveClass(job.live)">{{ liveLabel(job.live) }}</dd>
          <dt>平台</dt><dd>{{ PLATFORM_ZH[job.platform] || job.platform }}</dd>
          <template v-if="paused">
            <dt>画质</dt><dd>{{ QUALITY_ZH[job.quality] || job.quality || "原画" }}</dd>
          </template>
          <template v-else>
            <dt>进程</dt><dd>PID {{ job.pid || "—" }} · 内存 {{ fmtBytes(job.memory) }}</dd>
          </template>
          <dt>运行时长</dt><dd>{{ startedText }}</dd>
          <dt>单元</dt><dd class="wrap">{{ job.unit }}</dd>
        </dl>
        <div class="detail-actions">
          <button class="secondary" type="button" @click="navigate('/tasks')">返回任务</button>
          <button v-if="paused" class="secondary" type="button" :disabled="busy" @click="askResume(job)">{{ pending && taskState.pendingAction === 'resume' ? "继续中…" : "继续" }}</button>
          <template v-else>
            <button class="secondary" type="button" :disabled="busy || !canPause" @click="askPause(job)">{{ stopping || (pending && taskState.pendingAction === 'pause') ? "暂停中…" : "暂停" }}</button>
            <button class="secondary" type="button" :disabled="busy" @click="askRestart(job)">{{ pending && taskState.pendingAction === 'restart' ? "重启中…" : "重启" }}</button>
          </template>
          <button class="danger" type="button" :disabled="busy" @click="askDeleteTask(job, () => navigate('/tasks'))">{{ pending && taskState.pendingAction === 'delete' ? "删除中…" : "删除" }}</button>
        </div>
      </section>
      <section class="panel">
        <div class="panel-title">
          <div class="title-wrap">
            <span class="section-icon"><AppIcon name="terminal" /></span>
            <div><h2>任务日志</h2><span class="panel-kicker">Journal 实时输出</span></div>
          </div>
            <button class="secondary" type="button" @click="navigate('/library')">录制文件</button>
        </div>
        <LogPanel :unit="unit" />
      </section>
    </div>
  </div>
</template>
<script setup>
import { computed } from "vue";
import AppIcon from "../features/app/AppIcon.vue";
import LogPanel from "../features/logs/LogPanel.vue";
import { taskState } from "../stores/taskStore.js";
import { PLATFORM_ZH, QUALITY_ZH, stateLabel, liveClass, liveLabel, isStopping, isPaused, fmtBytes, fmtUptime } from "../utils.js";
import { navigate } from "../router.js";
import { askPause, askResume, askRestart, askDeleteTask } from "../features/tasks/taskActions.js";

const props = defineProps({ unit: { type: String, required: true } });

const job = computed(() => taskState.jobs.find((j) => j.unit === props.unit));
const pending = computed(() => taskState.pendingUnit === props.unit);
// 与任务卡片一致：systemd 正在收尾（deactivating）或请求在途都算"暂停中"。
const stopping = computed(() => isStopping(job.value));
const paused = computed(() => isPaused(job.value));
const busy = computed(() => pending.value || stopping.value);
// 只有运行中的任务可以暂停；已停止/失败的任务直接删除即可。
const canPause = computed(() => Boolean(job.value) && job.value.state !== "inactive" && job.value.state !== "failed");
const startedText = computed(() => {
  if (!job.value) return "启动时间未知";
  if (paused.value) return "已暂停";
  return job.value.state === "active" ? "已运行 " + fmtUptime(job.value.started) : job.value.started ? new Date(job.value.started).toLocaleString() : "启动时间未知";
});
</script>
