<template>
  <article class="job" :class="{ sel: selected }" :data-state="job.state">
    <div class="logo" :style="{ color: logoColor }">{{ (job.platform || "?").slice(0, 2) }}</div>
    <div class="job-main">
      <div class="job-heading">
        <button class="job-title link-button" type="button" :title="job.target" @click="$emit('open', job)">{{ job.target }}</button>
        <span class="platform-tag">{{ platformZh }}</span>
      </div>
      <div class="job-facts">
        <span class="status" :class="stateClass(job.state, job.substate)">{{ stateLabel(job.state, job.substate) }}</span>
        <span>PID {{ job.pid || "—" }}</span>
        <span>内存 {{ fmtBytes(job.memory) }}</span>
        <span v-if="job.restarts">重启 {{ job.restarts }}</span>
        <span v-if="job.state === 'active'">已运行 {{ fmtUptime(job.started) }}</span>
      </div>
    </div>
    <div class="actions">
      <button class="secondary" type="button" :disabled="pending" @click="$emit('open', job)">日志</button>
      <button class="secondary optional-action" type="button" :disabled="pending" @click="copy">复制名称</button>
      <button class="secondary optional-action" type="button" :disabled="pending" @click="$emit('restart', job)">{{ pending && taskState.pendingAction === 'restart' ? "重启中…" : "重启" }}</button>
      <button class="danger" type="button" :disabled="pending || !canStop" @click="$emit('stop', job)">{{ pending && taskState.pendingAction === 'stop' ? "停止中…" : "停止" }}</button>
    </div>
  </article>
</template>
<script setup>
import { computed } from "vue";
import { PLATFORM_ZH, LOGO_COLORS, stateClass, stateLabel, fmtBytes, fmtUptime } from "../../utils.js";
import { toast } from "../../ui.js";
import { taskState } from "../../stores/taskStore.js";

const props = defineProps({ job: { type: Object, required: true }, selected: Boolean });
defineEmits(["open", "restart", "stop"]);
const platformZh = PLATFORM_ZH[props.job.platform] || props.job.platform || "—";
const logoColor = LOGO_COLORS[props.job.platform] || "var(--blue)";
const pending = computed(() => taskState.pendingUnit === props.job.unit);
const canStop = computed(() => props.job.state === "active" || props.job.substate === "deactivating");

async function copy() {
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(props.job.unit);
    else {
      const input = document.createElement("textarea");
      input.value = props.job.unit;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      if (!document.execCommand("copy")) throw new Error("copy failed");
      input.remove();
    }
    toast("任务名称已复制");
  } catch { toast("复制失败，请手动选择文本"); }
}
</script>
