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
          <button class="mini secondary" type="button" :disabled="state.filesBusy" @click="loadFiles">{{ state.filesBusy ? "加载中…" : "刷新" }}</button>
        </div>
      </div>
      <FileList
        :files="state.files"
        :total="state.filesTotal"
        remote-search
        :loading="state.filesBusy && !state.files.length"
        :loading-more="state.filesBusy && !!state.files.length"
        :error="state.errors.files"
        @search="onSearch"
        @load-more="loadMore"
        @retry="loadFiles"
        @delete="askDeleteFile"
      />
    </section>
  </div>
</template>
<script setup>
import { computed, ref, watch, onMounted } from "vue";
import FileList from "../components/FileList.vue";
import { state, refreshFiles, loadMoreFiles } from "../store.js";
import { PLATFORM_ZH } from "../utils.js";
import { askDeleteFile } from "../actions.js";

const platformFilter = ref("all");
const fileQuery = ref("");

const platforms = ["tiktok", "douyin", "soop", "kick", "youtube", "chzzk"];
const countText = computed(() => (state.files.length ? `${state.filesTotal || state.files.length} 个` : "无文件"));

const effectiveQuery = computed(() => {
  const parts = [fileQuery.value.trim()];
  if (platformFilter.value !== "all") parts.push(platformFilter.value);
  return parts.filter(Boolean).join(" ");
});

async function loadFiles() {
  state.filesQuery = effectiveQuery.value;
  try {
    await refreshFiles({ query: effectiveQuery.value, offset: 0 });
  } catch {
    // 错误已写入全局状态，由 FileList 展示重试入口。
  }
}
function onSearch(value) {
  fileQuery.value = value;
  loadFiles();
}
async function loadMore() {
  try {
    await loadMoreFiles();
  } catch {
    // 错误已写入全局状态。
  }
}
watch(platformFilter, loadFiles);
onMounted(() => {
  if (state.filesQuery !== effectiveQuery.value) loadFiles();
});
</script>
<style scoped>
.files-panel .log-tools select { width: auto; }
</style>
