<template>
  <div class="log-console">
    <div class="log-tools">
      <label><input v-model="autoLog" type="checkbox"> 自动刷新</label>
      <select v-model="tail" aria-label="日志行数">
        <option value="200">200 行</option>
        <option value="1000">1000 行</option>
        <option value="5000">5000 行</option>
      </select>
      <button class="mini secondary" type="button" @click="wrap = !wrap">{{ wrap ? "关闭换行" : "开启换行" }}</button>
      <button class="mini secondary" type="button" @click="errorsOnly = !errorsOnly">
        {{ errorsOnly ? "全部日志" : "只显示错误" }}
      </button>
      <button class="mini secondary" type="button" @click="clear">清屏</button>
      <button class="mini secondary" type="button" @click="copy">复制日志</button>
    </div>
    <div v-if="loading" class="loading-state" role="status">正在加载日志…</div>
    <div v-else-if="error" class="error-state" role="alert">{{ error }}</div>
    <pre v-else ref="logEl" :class="{ nowrap: !wrap }" class="logs">{{ displayed || "暂无日志" }}</pre>
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
const loading = ref(false);
const error = ref("");
const logEl = ref(null);
let timer = null;
let requestId = 0;

const displayed = computed(() => {
  let lines = rawLines.value;
  if (errorsOnly.value) {
    lines = lines.filter((l) => /error|fail|exception|panic|ERR/i.test(l));
  }
  return lines.join("\n");
});

async function fetchLogs() {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  try {
    const text = await logs(props.unit, Number(tail.value));
    if (currentRequest !== requestId) return;
    rawLines.value = text.split("\n");
    await nextTick();
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
  } catch (e) {
    if (currentRequest !== requestId) return;
    error.value = e.message || "日志加载失败";
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function toggleWrap() {
  wrap.value = !wrap.value;
}

function clear() {
  rawLines.value = [];
  toast("日志已清屏，自动刷新后会重新显示");
}

async function copy() {
  try {
    if (!navigator.clipboard) throw new Error("clipboard unavailable");
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
