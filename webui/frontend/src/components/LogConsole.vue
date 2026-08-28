<template>
  <div class="log-console">
    <div class="log-tools">
      <label><input v-model="autoLog" type="checkbox"> 自动刷新</label>
      <select v-model="tail" aria-label="日志行数">
        <option value="200">200 行</option>
        <option value="1000">1000 行</option>
        <option value="5000">5000 行</option>
      </select>
      <button class="mini secondary" @click="wrap = !wrap">{{ wrap ? "换行" : "不换行" }}</button>
      <button class="mini secondary" @click="errorsOnly = !errorsOnly">
        {{ errorsOnly ? "全部日志" : "只显示错误" }}
      </button>
      <button class="mini secondary" @click="clear">清空</button>
      <button class="mini secondary" @click="copy">复制</button>
    </div>
    <pre ref="logEl" :class="{ nowrap: !wrap }" class="logs">{{ displayed }}</pre>
  </div>
</template>
<script setup>
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from "vue";
import { logs } from "../store.js";
import { toast } from "../ui.js";

const props = defineProps({ unit: { type: String, required: true } });

const rawLines = ref([]);
const autoLog = ref(true);
const tail = ref("200");
const wrap = ref(true);
const errorsOnly = ref(false);
const logEl = ref(null);
let timer = null;

const displayed = computed(() => {
  let lines = rawLines.value;
  if (errorsOnly.value) {
    lines = lines.filter((l) => /error|fail|exception|panic|ERR/i.test(l));
  }
  return lines.join("\n");
});

async function fetchLogs() {
  try {
    const text = await logs(props.unit, Number(tail.value));
    rawLines.value = text.split("\n");
    await nextTick();
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
  } catch (e) {
    rawLines.value = [e.message];
  }
}

function toggleWrap() {
  wrap.value = !wrap.value;
}

function clear() {
  rawLines.value = [];
  toast("日志已清空");
}

async function copy() {
  try {
    await navigator.clipboard.writeText(displayed.value);
    toast("日志已复制");
  } catch {
    toast("复制失败，请手动选择文本");
  }
}

onMounted(() => {
  fetchLogs();
  timer = setInterval(() => {
    if (autoLog.value) fetchLogs();
  }, 5000);
});
onUnmounted(() => clearInterval(timer));
watch(() => props.unit, fetchLogs);
watch(tail, fetchLogs);
</script>
