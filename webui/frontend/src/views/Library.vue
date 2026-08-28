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
            <option value="">全部平台</option>
            <option v-for="p in platforms" :key="p" :value="p">{{ PLATFORM_ZH[p] || p }}</option>
          </select>
          <button class="mini secondary" @click="refreshAll">刷新</button>
        </div>
      </div>
      <FileList :files="filtered" @play="playFile" @delete="askDeleteFile" />
    </section>
  </div>
</template>
<script setup>
import { computed, ref } from "vue";
import FileList from "../components/FileList.vue";
import { state, refreshAll } from "../store.js";
import { PLATFORM_ZH } from "../utils.js";
import { playFile, askDeleteFile } from "../actions.js";

const platformFilter = ref("");

const platforms = computed(() => {
  const set = new Set();
  for (const f of state.files) {
    const top = f.dir.split("/")[0];
    if (top) set.add(top);
  }
  return [...set];
});
const filtered = computed(() =>
  platformFilter.value ? state.files.filter((f) => f.dir.split("/")[0] === platformFilter.value) : state.files
);
const countText = computed(() => (state.files.length ? `${state.filesTotal || state.files.length} 个` : "无文件"));
</script>
<style scoped>
.files-panel .log-tools select { width: auto; }
</style>
