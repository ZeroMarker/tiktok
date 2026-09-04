<template>
  <div class="library">
    <section class="panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon"><AppIcon name="library" /></span>
          <div>
            <h2>录制文件<span class="count">{{ countText }}</span></h2>
            <span class="panel-kicker">按平台/目录浏览，播放、下载或清理</span>
          </div>
        </div>
        <div class="seg" role="tablist" aria-label="平台过滤">
          <button class="seg-btn" :class="{ on: platformFilter === 'all' }" type="button" @click="platformFilter = 'all'">全部</button>
          <button v-for="p in platforms" :key="p" class="seg-btn" :class="{ on: platformFilter === p }" type="button" @click="platformFilter = p">{{ PLATFORM_ZH[p] || p }}</button>
        </div>
        <button class="mini secondary" type="button" :disabled="recordingState.busy" @click="loadFiles">{{ recordingState.busy ? "加载中…" : "刷新" }}</button>
      </div>
      <FileBrowser
        :files="visibleFiles"
        :total="visibleTotal"
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
import AppIcon from "../features/app/AppIcon.vue";
import FileBrowser from "../features/recordings/FileBrowser.vue";
import { recordingState, refreshRecordings, loadMoreRecordings } from "../stores/recordingStore.js";
import { PLATFORM_ZH } from "../utils.js";
import { askDeleteRecording } from "../features/recordings/recordingActions.js";

const platformFilter = ref("all");
const fileQuery = ref("");

const platforms = ["tiktok", "douyin", "soop", "kick", "youtube", "chzzk"];
const countText = computed(() => (visibleFiles.value.length ? `${visibleTotal.value} 个` : "无文件"));

// 平台过滤在客户端按顶层目录（recordings/<platform>/…）判定：
// 后端 q 是整体子串匹配，把平台名拼进 q 会导致组合条件永远为空。
const visibleFiles = computed(() => {
  if (platformFilter.value === "all") return recordingState.files;
  return recordingState.files.filter((file) => (file.dir || "").split("/")[0] === platformFilter.value);
});
const visibleTotal = computed(() => (platformFilter.value === "all" ? recordingState.total : visibleFiles.value.length));

async function loadFiles() {
  const query = fileQuery.value.trim();
  recordingState.query = query;
  // 平台过滤时一次取足（后端上限 500），保证过滤视图完整，同时让后台同步/删除后刷新沿用同一条数。
  recordingState.limit = platformFilter.value === "all" ? 80 : 500;
  try {
    await refreshRecordings({ query, offset: 0 });
  } catch {
    // 错误已写入录制文件状态，由 FileBrowser 展示重试入口。
  }
}
function onSearch(value) {
  fileQuery.value = value;
  loadFiles();
}
async function loadMore() {
  if (platformFilter.value !== "all") return;
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
