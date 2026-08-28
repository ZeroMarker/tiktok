<template>
  <form class="start-grid" @submit.prevent="submit">
    <div class="field-group">
      <label for="platform">平台</label>
      <select id="platform" v-model="platform" aria-describedby="platform-hint">
        <option v-for="name in PLATFORM_KEYS" :key="name" :value="name">{{ PLATFORM_ZH[name] }}</option>
      </select>
    </div>
    <div class="field-group field-target">
      <label for="target">频道或直播地址</label>
      <input id="target" v-model="target" required :placeholder="placeholder" aria-describedby="target-hint" autocomplete="off">
    </div>
    <div class="field-group">
      <label for="quality">录制画质</label>
      <select id="quality" v-model="quality">
        <option v-for="value in QUALITIES" :key="value" :value="value">{{ QUALITY_ZH[value] }}</option>
      </select>
    </div>
    <button type="submit" :disabled="submitting" :aria-busy="submitting">{{ submitting ? "创建中…" : "开始录制" }}</button>
    <div v-if="platform === 'douyin'" class="field-group cookie-row">
      <label for="cookie-file">Cookie 文件路径（可选）</label>
      <input id="cookie-file" v-model="cookie" placeholder="例如：/secure/douyin-cookies.txt" aria-describedby="cookie-hint">
    </div>
  </form>
  <div id="platform-hint" class="hint">{{ hint }}</div>
  <div id="target-hint" class="form-help">输入用户名、频道 ID 或完整直播地址。</div>
  <div v-if="platform === 'douyin'" id="cookie-hint" class="form-help">Cookie 文件留在服务器本机，不会上传到浏览器。</div>
  <div v-if="errorMessage" class="inline-error" role="alert">{{ errorMessage }}</div>
</template>
<script setup>
import { computed, ref } from "vue";
import { taskState, startTask } from "../../stores/taskStore.js";
import { refreshAll } from "../../stores/syncStore.js";
import { navigate } from "../../router.js";
import { toast } from "../../ui.js";
import { PLATFORM_KEYS, PLATFORM_ZH, PLATFORM_HINTS, QUALITIES, QUALITY_ZH } from "../../config/platforms.js";

const platform = ref("tiktok");
const target = ref("");
const quality = ref("best");
const cookie = ref("");
const submitting = ref(false);
const errorMessage = ref("");
const placeholder = computed(() => PLATFORM_HINTS[platform.value][0]);
const hint = computed(() => PLATFORM_HINTS[platform.value][1]);

async function submit() {
  errorMessage.value = "";
  const value = target.value.trim();
  if (!value) return toast("请输入频道或直播地址");
  const duplicate = taskState.jobs.some((job) => job.platform === platform.value && (job.target || "").trim().toLowerCase() === value.toLowerCase());
  if (duplicate) return toast("该频道已存在录制任务，请勿重复添加");
  submitting.value = true;
  try {
    const data = await startTask({ platform: platform.value, target: value, quality: quality.value, cookie_file: cookie.value.trim() });
    toast("任务已启动");
    target.value = "";
    taskState.selectedUnit = data.unit;
    await refreshAll({ includeFiles: false });
    navigate("/tasks/" + encodeURIComponent(data.unit));
  } catch (error) {
    errorMessage.value = error.message;
    toast(error.message);
  } finally {
    submitting.value = false;
  }
}
</script>
