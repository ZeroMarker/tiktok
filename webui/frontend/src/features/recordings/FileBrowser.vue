<template>
  <div class="files-panel">
    <FileToolbar :query="remoteSearch ? query : localQuery" @search="onSearch" @expand-all="expandAll" />
    <MediaPlayer :file="playing" @close="closePlayer" @error="playerError" />
    <div v-if="loading && !files.length" class="loading-state" role="status">正在加载文件…</div>
    <div v-else-if="error && !files.length" class="error-state" role="alert"><span>{{ error }}</span><button class="mini secondary" type="button" @click="$emit('retry')">重试</button></div>
    <div v-else-if="!groups.length" class="empty"><strong>{{ activeQuery ? "没有匹配的文件" : "暂无录制文件" }}</strong><span>{{ activeQuery ? "请尝试其他关键词" : "录制完成后，文件会显示在这里" }}</span></div>
    <div v-else class="files">
      <FileGroup v-for="group in groups" :key="group.dir" :group="group" :open="isOpen(group.dir)" :active-path="playing && playing.path" :pending-path="pendingPath" @toggle="toggle" @play="play" @delete="$emit('delete', $event)" />
      <div v-if="error" class="inline-error" role="alert">{{ error }} <button class="mini secondary" type="button" @click="$emit('retry')">重试</button></div>
      <button v-if="hasMore" class="load-more" type="button" :disabled="loading" @click="$emit('load-more')">{{ loading ? "加载中…" : `加载更多（${files.length}/${total}）` }}</button>
    </div>
  </div>
</template>
<script setup>
import { computed, ref } from "vue";
import FileToolbar from "./FileToolbar.vue";
import FileGroup from "./FileGroup.vue";
import MediaPlayer from "./MediaPlayer.vue";

const props = defineProps({ files: { type: Array, default: () => [] }, total: Number, query: String, remoteSearch: Boolean, loading: Boolean, error: String, pendingPath: String });
const emit = defineEmits(["search", "retry", "load-more", "delete"]);
const playing = ref(null);
const collapsed = ref(null);
const localQuery = ref("");
const activeQuery = computed(() => props.remoteSearch ? (props.query || "") : localQuery.value);
const displayFiles = computed(() => {
  if (props.remoteSearch || !localQuery.value.trim()) return props.files;
  const query = localQuery.value.trim().toLowerCase();
  return props.files.filter((file) => (file.name + " " + file.dir).toLowerCase().includes(query));
});
const groups = computed(() => {
  const map = new Map();
  for (const file of displayFiles.value) {
    const dir = file.dir || "";
    if (!map.has(dir)) map.set(dir, { dir, name: dir || "根目录", files: [] });
    map.get(dir).files.push(file);
  }
  return [...map.values()];
});
const hasMore = computed(() => props.remoteSearch && props.files.length < (props.total || 0));
function onSearch(value) {
  if (props.remoteSearch) emit("search", value);
  else localQuery.value = value;
}
function isOpen(dir) { return collapsed.value === null ? groups.value[0]?.dir === dir : !collapsed.value.has(dir); }
function toggle(dir) {
  if (collapsed.value === null) collapsed.value = new Set(groups.value.map((group) => group.dir));
  if (collapsed.value.has(dir)) collapsed.value.delete(dir); else collapsed.value.add(dir);
  collapsed.value = new Set(collapsed.value);
}
function expandAll(open) { collapsed.value = new Set(open ? [] : displayFiles.value.map((file) => file.dir)); }
function play(file) { playing.value = file; }
function closePlayer() { playing.value = null; }
function playerError() { /* video 元素已提供错误反馈，避免打断列表操作 */ }
</script>
