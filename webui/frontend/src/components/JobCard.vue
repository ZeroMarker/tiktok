<template>
  <article class="job" :class="{ sel: selected }" :data-state="job.state">
    <div class="logo" :style="{ color: logoColor }">{{ (job.platform || "?").slice(0, 2) }}</div>
    <div class="job-main">
      <div class="job-heading">
        <h3 class="job-title" :title="job.target" @click="$emit('open', job)">{{ job.target }}</h3>
        <span class="platform-tag">{{ platformZh }}</span>
      </div>
      <div class="job-facts">
        <span class="status" :class="stateClass(job.state, job.substate)">
          {{ stateLabel(job.state, job.substate) }}
        </span>
        <span>PID {{ job.pid || "—" }}</span>
        <span>内存 {{ fmtBytes(job.memory) }}</span>
        <span v-if="job.restarts">重启 {{ job.restarts }}</span>
        <span v-if="job.state === 'active'">已运行 {{ fmtUptime(job.started) }}</span>
      </div>
    </div>
    <div class="actions">
      <button class="secondary" @click="$emit('open', job)">日志</button>
      <button class="secondary" @click="copy">复制名称</button>
      <button class="secondary" @click="$emit('restart', job)">重启</button>
      <button class="danger" @click="$emit('stop', job)">停止</button>
    </div>
  </article>
</template>
<script setup>
import {
  PLATFORM_ZH,
  LOGO_COLORS,
  stateClass,
  stateLabel,
  fmtBytes,
  fmtUptime,
} from "../utils.js";
import { toast } from "../ui.js";

const props = defineProps({
  job: { type: Object, required: true },
  selected: Boolean,
});
defineEmits(["open", "restart", "stop"]);

const platformZh = (PLATFORM_ZH[props.job.platform] || props.job.platform || "—");
const logoColor = LOGO_COLORS[props.job.platform] || "var(--blue)";

async function copy() {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(props.job.unit);
      toast("任务名称已复制");
      return;
    }
    const input = document.createElement("textarea");
    input.value = props.job.unit;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
    toast("任务名称已复制");
  } catch {
    toast("复制失败，请手动选择文本");
  }
}
</script>
