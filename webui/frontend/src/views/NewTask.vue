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
        <select v-model="platform" aria-label="选择平台">
          <option value="tiktok">TikTok</option>
          <option value="douyin">抖音</option>
          <option value="soop">SOOP</option>
          <option value="kick">Kick</option>
          <option value="youtube">YouTube</option>
          <option value="chzzk">CHZZK</option>
        </select>
        <input v-model="target" required :placeholder="placeholder" aria-label="频道或直播地址">
        <select v-model="quality" aria-label="录制画质">
          <option v-for="q in QUALITIES" :key="q" :value="q">{{ QUALITY_ZH[q] }}</option>
        </select>
        <button type="submit" :disabled="submitting">{{ submitting ? "启动中…" : "开始录制" }}</button>
        <input
          v-if="platform === 'douyin'"
          v-model="cookie"
          class="cookie-row"
          placeholder="抖音 Cookie 文件路径（仅抖音可选）"
          aria-label="抖音 Cookie 文件路径"
        >
      </form>
      <div class="hint">{{ hint }}</div>
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

const placeholder = computed(() => hints[platform.value][0]);
const hint = computed(() => hints[platform.value][1]);

async function submit() {
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
    toast(e.message);
  } finally {
    submitting.value = false;
  }
}
</script>
