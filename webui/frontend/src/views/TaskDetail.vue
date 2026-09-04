<template>
  <div class="task-detail">
    <section v-if="!job" class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
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
            <span class="section-icon" aria-hidden="true">●</span>
            <div>
              <h2>{{ job.target }}<span class="platform-tag">{{ PLATFORM_ZH[job.platform] || job.platform }}</span></h2>
              <span class="panel-kicker">{{ stateLabel(job.state, job.substate) }}</span>
            </div>
          </div>
        </div>
        <dl class="kv">
          <dt>状态</dt><dd>{{ stateLabel(job.state, job.substate) }}</dd>
          <dt>平台</dt><dd>{{ PLATFORM_ZH[job.platform] || job.platform }}</dd>
          <dt>进程</dt><dd>PID {{ job.pid || "—" }} · 内存 {{ fmtBytes(job.memory) }}</dd>
          <dt>运行时长</dt><dd>{{ startedText }}</dd>
          <dt>单元</dt><dd class="wrap">{{ job.unit }}</dd>
        </dl>
        <div class="detail-actions">
          <button class="secondary" type="button" @click="navigate('/tasks')">返回任务</button>
          <button class="secondary" type="button" :disabled="pending" @click="askRestart(job)">{{ pending && taskState.pendingAction === 'restart' ? "重启中…" : "重启" }}</button>
          <button class="danger" type="button" :disabled="pending || !canStop" @click="askStop(job, () => navigate('/tasks'))">{{ pending && taskState.pendingAction === 'stop' ? "停止中…" : "停止" }}</button>
        </div>
      </section>
      <section class="panel">
        <div class="panel-title">
          <div class="title-wrap">
            <span class="section-icon" aria-hidden="true">›_</span>
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
import LogPanel from "../features/logs/LogPanel.vue";
import { taskState } from "../stores/taskStore.js";
import { navigate } from "../router.js";
import { PLATFORM_ZH, stateLabel, fmtBytes, fmtUptime } from "../utils.js";
import { askStop, askRestart } from "../features/tasks/taskActions.js";

const props = defineProps({ unit: { type: String, required: true } });

const job = computed(() => taskState.jobs.find((j) => j.unit === props.unit));
const pending = computed(() => taskState.pendingUnit === props.unit);
const canStop = computed(() => job.value && (job.value.state === "active" || job.value.substate === "deactivating"));
const startedText = computed(() => {
  if (!job.value) return "启动时间未知";
  return job.value.state === "active" ? "已运行 " + fmtUptime(job.value.started) : job.value.started ? new Date(job.value.started).toLocaleString() : "启动时间未知";
});
</script>
