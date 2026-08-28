<template>
  <div class="library">
    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon" aria-hidden="true">□</span>
          <div>
            <h2>录制文件<span class="count">{{ countText }}</span></h2>
            <span class="panel-kicker">按平台/目录浏览，播放、下载或清理</span>
          </div>
        </div>
        <div class="log-tools">
          <select v-model="platformFilter" aria-label="平台过滤">
            <option value="all">全部平台</option>
            <option v-for="p in platforms" :key="p" :value="p">{{ PLATFORM_ZH[p] || p }}</option>
          </select>
          <button class="mini secondary" type="button" :disabled="recordingState.busy" @click="loadFiles">{{ recordingState.busy ? "加载中…" : "刷新" }}</button>
        </div>
      </div>
      <FileBrowser
        :files="recordingState.files"
        :total="recordingState.total"
        :query="fileQuery"
        remote-search
        :loading="recordingState.busy"
        :error="recordingState.error"
        :pending-path="recordingState.pendingPath"
        @search="onSearch"
        @load-more="loadMore"
        @retry="loadFiles"
        @delete="askDeleteRecording"
      />
    </section>
  </div>
</template>
<script setup>
import { computed, ref, watch, onMounted } from "vue";
import FileBrowser from "../features/recordings/FileBrowser.vue";
import { recordingState, refreshRecordings, loadMoreRecordings } from "../stores/recordingStore.js";
import { PLATFORM_ZH } from "../utils.js";
import { askDeleteRecording } from "../features/recordings/recordingActions.js";

const platformFilter = ref("all");
const fileQuery = ref("");

const platforms = ["tiktok", "douyin", "soop", "kick", "youtube", "chzzk"];
const countText = computed(() => (recordingState.files.length ? `${recordingState.total || recordingState.files.length} 个` : "无文件"));

const effectiveQuery = computed(() => {
  const parts = [fileQuery.value.trim()];
  if (platformFilter.value !== "all") parts.push(platformFilter.value);
  return parts.filter(Boolean).join(" ");
});

async function loadFiles() {
  recordingState.query = effectiveQuery.value;
  try {
    await refreshRecordings({ query: effectiveQuery.value, offset: 0 });
  } catch {
    // 错误已写入录制文件状态，由 FileBrowser 展示重试入口。
  }
}
function onSearch(value) {
  fileQuery.value = value;
  loadFiles();
}
async function loadMore() {
  try {
    await loadMoreRecordings();
  } catch {
    // 错误已写入全局状态。
  }
}
watch(platformFilter, loadFiles);
onMounted(() => {
  loadFiles();
});
</script>
<style scoped>
.files-panel .log-tools select { width: auto; }
</style>
