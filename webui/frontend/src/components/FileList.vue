<template>
  <div class="files-panel">
    <div class="log-tools">
      <input v-model="query" placeholder="搜索…" aria-label="搜索文件" style="width:110px">
      <button class="mini secondary" @click="expandAll(true)">展开</button>
      <button class="mini secondary" @click="expandAll(false)">收起</button>
    </div>
    <div v-if="!shown.length" class="empty">{{ query ? "无匹配文件" : "暂无录制文件" }}</div>
    <div v-else class="files">
      <div v-for="g in groups" :key="g.dir" class="fgroup" :class="{ open: !collapsed.has(g.dir) }">
        <button class="fgroup-head" @click="toggle(g.dir)">
          <span class="chevron">▶</span>
          <span>{{ g.name }}</span>
          <span class="count">{{ g.files.length }} 个文件</span>
        </button>
        <div class="fgroup-body">
          <div v-for="f in g.files" :key="f.path" class="file-row">
            <div class="fname" :title="f.path">
              <a :href="fileUrl(f.path)" download>{{ f.name }}</a>
            </div>
            <div class="fmeta">{{ fmtBytes(f.size) }} · {{ fmtDate(f.modified) }}</div>
            <div class="file-actions">
              <button class="mini secondary" @click="$emit('play', f)">播放</button>
              <button class="mini danger" @click="$emit('delete', f)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, computed } from "vue";
import { fmtBytes, fileUrl } from "../utils.js";

const props = defineProps({ files: { type: Array, default: () => [] } });
defineEmits(["play", "delete"]);

const query = ref("");
const collapsed = ref(new Set());

const shown = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return props.files;
  return props.files.filter((f) => (f.name + " " + f.dir).toLowerCase().includes(q));
});

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

function toggle(dir) {
  if (collapsed.value.has(dir)) collapsed.value.delete(dir);
  else collapsed.value.add(dir);
  collapsed.value = new Set(collapsed.value);
}

function expandAll(open) {
  collapsed.value = new Set(open ? [] : props.files.map((f) => f.dir));
}

function fmtDate(t) {
  return new Date(t * 1000).toLocaleString();
}
</script>
