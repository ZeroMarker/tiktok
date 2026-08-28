<template>
  <div class="task-detail">
    <section v-if="job" class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
          <div>
            <h2>{{ job.target }}<span class="platform-tag">{{ PLATFORM_ZH[job.platform] || job.platform }}</span></h2>
            <span class="panel-kicker">
              {{ stateLabel(job.state, job.substate) }} · PID {{ job.pid || "—" }} · 内存 {{ fmtBytes(job.memory) }}
              · {{ startedText }}
            </span>
          </div>
        </div>
        <div class="actions">
          <button class="secondary" @click="navigate('/tasks')">返回任务</button>
          <button class="secondary" @click="navigate('/new')">新建</button>
          <button class="secondary" @click="askRestart(job)">重启</button>
          <button class="danger" @click="askStop(job, () => navigate('/tasks'))">停止</button>
        </div>
      </div>
    </section>

    <section v-else class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">●</span>
          <div><h2>任务详情</h2><span class="panel-kicker">{{ unit }}</span></div>
        </div>
        <div class="actions">
          <button class="secondary" @click="navigate('/tasks')">返回任务</button>
        </div>
      </div>
      <div class="hint warn">该任务当前不在 systemd 单元列表中（可能已移除），仍可查看最近日志。</div>
    </section>

    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">›_</span>
          <div><h2>任务日志</h2><span class="panel-kicker">Journal 实时输出</span></div>
        </div>
        <button class="secondary" @click="navigate('/library')">文件库</button>
      </div>
      <LogConsole :unit="unit" />
    </section>
  </div>
</template>
<script setup>
import { computed } from "vue";
import LogConsole from "../components/LogConsole.vue";
import { state } from "../store.js";
import { navigate } from "../router.js";
import { PLATFORM_ZH, stateLabel, fmtBytes, fmtUptime } from "../utils.js";
import { askStop, askRestart } from "../actions.js";

const props = defineProps({ unit: { type: String, required: true } });

const job = computed(() => state.jobs.find((j) => j.unit === props.unit));
const startedText = computed(() => {
  if (!job.value) return "启动时间未知";
  return job.value.state === "active" ? "已运行 " + fmtUptime(job.value.started) : job.value.started ? new Date(job.value.started).toLocaleString() : "启动时间未知";
});
</script>
