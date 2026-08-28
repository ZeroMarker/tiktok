<template>
  <div class="files-panel">
    <div class="log-tools">
      <input v-model="query" class="file-search" placeholder="搜索文件名或目录" aria-label="搜索文件" @input="searchChanged(query)">
      <button class="mini secondary" type="button" @click="expandAll(true)">全部展开</button>
      <button class="mini secondary" type="button" @click="expandAll(false)">全部收起</button>
    </div>

    <div v-if="playing" ref="playerEl" class="inline-player">
      <div class="inline-player-head">
        <span class="player-title" :title="playing.path">{{ playing.name }}</span>
        <span class="fmeta">{{ fmtBytes(playing.size) }} · {{ fmtDate(playing.modified) }}</span>
        <a :href="fileUrl(playing.path)" download class="mini secondary">下载</a>
        <button class="mini secondary" type="button" @click="closePlayer">收起播放器</button>
      </div>
      <video ref="videoEl" :key="playing.path" controls autoplay playsinline :src="fileUrl(playing.path)"></video>
    </div>

    <div v-if="loading" class="loading-state" role="status">正在加载文件…</div>
    <div v-else-if="error" class="error-state" role="alert">
      <span>{{ error }}</span>
      <button class="mini secondary" type="button" @click="$emit('retry')">重试</button>
    </div>
    <div v-else-if="!shown.length" class="empty">
      <strong>{{ query ? "没有匹配的文件" : "暂无录制文件" }}</strong>
      <span>{{ query ? "请尝试其他关键词" : "录制完成后，文件会显示在这里" }}</span>
    </div>
    <div v-else class="files">
      <div v-for="g in groups" :key="g.dir" class="fgroup" :class="{ open: isOpen(g.dir) }">
        <button class="fgroup-head" type="button" :aria-expanded="isOpen(g.dir)" @click="toggle(g.dir)">
          <span class="chevron">▶</span>
          <span>{{ g.name }}</span>
          <span class="count">{{ g.files.length }} 个文件</span>
        </button>
        <div class="fgroup-body">
          <div v-for="f in g.files" :key="f.path" class="file-row" :class="{ active: playing && playing.path === f.path }">
            <div class="fname" :title="f.path">
              <a :href="fileUrl(f.path)" download>{{ f.name }}</a>
            </div>
            <div class="fmeta">{{ fmtBytes(f.size) }} · {{ fmtDate(f.modified) }}</div>
            <div class="file-actions">
              <button class="mini secondary" type="button" @click="play(f)">{{ playing && playing.path === f.path ? "播放中" : "播放" }}</button>
              <button class="mini danger" type="button" @click="$emit('delete', f)">删除</button>
            </div>
          </div>
        </div>
      </div>
      <button v-if="hasMore" class="load-more" type="button" :disabled="loadingMore" @click="$emit('load-more')">
        {{ loadingMore ? "加载中…" : `加载更多（${files.length}/${total}）` }}
      </button>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from "vue";
import { fmtBytes, fileUrl } from "../utils.js";

const props = defineProps({
  files: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  remoteSearch: Boolean,
  loading: Boolean,
  loadingMore: Boolean,
  error: { type: String, default: "" },
});
const emit = defineEmits(["delete", "search", "load-more", "retry"]);

const query = ref("");
const collapsed = ref(null);
const playing = ref(null);
const playerEl = ref(null);
const videoEl = ref(null);

const shown = computed(() => {
  if (props.remoteSearch) return props.files;
  const q = query.value.trim().toLowerCase();
  if (!q) return props.files;
  return props.files.filter((f) => (f.name + " " + f.dir).toLowerCase().includes(q));
});

let searchTimer = null;
function searchChanged(value) {
  if (!props.remoteSearch) return;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => emit("search", value), 250);
}

const groups = computed(() => {
  const map = {};
  const out = [];
  for (const f of shown.value) {
    const key = f.dir || "";
    if (!map[key]) {
      map[key] = { dir: key, name: key || "根目录", files: [] };
      out.push(map[key]);
    }
    map[key].files.push(f);
  }
  return out;
});

const hasMore = computed(() => props.remoteSearch && props.files.length < props.total);

function isOpen(dir) {
  if (collapsed.value === null) return groups.value[0] && groups.value[0].dir === dir;
  return !collapsed.value.has(dir);
}

function play(f) {
  playing.value = f;
  nextTick(() => {
    if (playerEl.value) playerEl.value.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (videoEl.value) videoEl.value.play().catch(() => {});
  });
}

function closePlayer() {
  const v = videoEl.value;
  if (v) {
    v.pause();
    v.removeAttribute("src");
    v.load();
  }
  playing.value = null;
}

function onKey(e) {
  if (e.key === "Escape" && playing.value) closePlayer();
}
onMounted(() => document.addEventListener("keydown", onKey));
onUnmounted(() => document.removeEventListener("keydown", onKey));

function toggle(dir) {
  if (collapsed.value === null) collapsed.value = new Set(groups.value.map((group) => group.dir));
  if (collapsed.value.has(dir)) collapsed.value.delete(dir);
  else collapsed.value.add(dir);
  collapsed.value = new Set(collapsed.value);
}

function expandAll(open) {
  collapsed.value = new Set(open ? [] : shown.value.map((f) => f.dir));
}

function fmtDate(t) {
  return new Date(t * 1000).toLocaleString();
}
</script>
<style scoped>
.inline-player {
  margin-bottom: 10px;
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  background: #050b0a;
  overflow: hidden;
}
.inline-player-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: rgba(13, 25, 24, 0.9);
  border-bottom: 1px solid var(--line);
}
.inline-player-head .player-title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 650;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.inline-player video {
  display: block;
  width: 100%;
  max-height: 52vh;
  background: #000;
}
.file-row.active {
  border-color: rgba(88, 224, 173, 0.5);
  box-shadow: inset 0 0 0 1px rgba(88, 224, 173, 0.15);
}
</style>
