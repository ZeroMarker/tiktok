<template>
  <div class="file-row" :class="{ active: active }">
    <div class="fname" :title="file.path"><a :href="fileUrl(file.path)" download>{{ file.name }}</a></div>
    <div class="fmeta">{{ fmtBytes(file.size) }} · {{ fmtDate(file.modified) }}</div>
    <div class="file-actions">
      <button class="mini secondary" type="button" @click="$emit('play', file)">{{ active ? "播放中" : "播放" }}</button>
      <button class="mini danger" type="button" :disabled="pending" @click="$emit('delete', file)">删除</button>
    </div>
  </div>
</template>
<script setup>
import { fileUrl, fmtBytes } from "../../utils.js";

defineProps({ file: { type: Object, required: true }, active: Boolean, pending: Boolean });
defineEmits(["play", "delete"]);
function fmtDate(timestamp) { return new Date(timestamp * 1000).toLocaleString(); }
</script>
