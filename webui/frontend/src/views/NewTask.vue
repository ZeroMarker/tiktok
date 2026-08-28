<template>
  <div class="new-task">
    <section class="panel create-panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">＋</span>
          <div><h2>新建录制</h2><span class="panel-kicker">选择平台并输入直播间信息</span></div>
        </div>
      </div>
      <form class="start-grid" @submit.prevent="submit">
        <div class="field-group">
          <label for="platform">平台</label>
          <select id="platform" v-model="platform" aria-describedby="platform-hint">
            <option value="tiktok">TikTok</option>
            <option value="douyin">抖音</option>
            <option value="soop">SOOP</option>
            <option value="kick">Kick</option>
            <option value="youtube">YouTube</option>
            <option value="chzzk">CHZZK</option>
          </select>
        </div>
        <div class="field-group field-target">
          <label for="target">频道或直播地址</label>
          <input id="target" v-model="target" required :placeholder="placeholder" aria-describedby="target-hint" autocomplete="off">
        </div>
        <div class="field-group">
          <label for="quality">录制画质</label>
          <select id="quality" v-model="quality">
            <option v-for="q in QUALITIES" :key="q" :value="q">{{ QUALITY_ZH[q] }}</option>
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
    </section>
  </div>
</template>
<script setup>
import { ref, computed } from "vue";
import { state, startJob, refreshAll } from "../store.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";
import { QUALITIES, QUALITY_ZH } from "../utils.js";

const hints = {
  tiktok: ["TikTok 用户名，如 akane.no.1", "输入 TikTok 用户名或完整直播地址。"],
  douyin: ["抖音 web_rid、抖音号或直播 URL", "可选 Cookie 文件适用于需要登录态的直播间。"],
  soop: ["SOOP 用户名或直播 URL", "输入主播用户名或 play.sooplive.co.kr 地址。"],
  kick: ["Kick 用户名或直播 URL", "输入 Kick 频道名或完整地址。"],
  youtube: ["YouTube @handle 或直播 URL", "支持频道直播页和具体直播链接。"],
  chzzk: ["CHZZK 频道 ID 或直播 URL", "输入频道 ID 或 chzzk.naver.com/live 地址。"],
};

const platform = ref("tiktok");
const target = ref("");
const quality = ref("best");
const cookie = ref("");
const submitting = ref(false);
const errorMessage = ref("");

const placeholder = computed(() => hints[platform.value][0]);
const hint = computed(() => hints[platform.value][1]);

async function submit() {
  errorMessage.value = "";
  const t = target.value.trim();
  if (!t) return toast("请输入频道或直播地址");
  const dup = state.jobs.some(
    (j) => j.platform === platform.value && (j.target || "").trim().toLowerCase() === t.toLowerCase()
  );
  if (dup) return toast("该频道已存在录制任务，请勿重复添加");
  submitting.value = true;
  try {
    const d = await startJob({ platform: platform.value, target: t, quality: quality.value, cookie_file: cookie.value.trim() });
    toast("任务已启动");
    target.value = "";
    state.selectedUnit = d.unit;
    await refreshAll();
    navigate("/tasks/" + encodeURIComponent(d.unit));
  } catch (e) {
    errorMessage.value = e.message;
    toast(e.message);
  } finally {
    submitting.value = false;
  }
}
</script>
