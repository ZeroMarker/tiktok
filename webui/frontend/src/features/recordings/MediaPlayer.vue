<template>
  <div v-if="file" ref="playerEl" class="inline-player">
    <div class="inline-player-head">
      <span class="player-title" :title="file.path">{{ file.name }}</span>
      <span class="fmeta">{{ fmtBytes(file.size) }} · {{ fmtDate(file.modified) }}</span>
      <a :href="fileUrl(file.path)" download class="mini secondary">下载</a>
      <button class="mini secondary" type="button" @click="$emit('close')">收起播放器</button>
    </div>
    <video ref="videoEl" :key="file.path" controls autoplay playsinline :src="fileUrl(file.path)" @error="$emit('error')"></video>
  </div>
</template>
<script setup>
import { nextTick, ref, watch } from "vue";
import { fmtBytes, fileUrl } from "../../utils.js";

const props = defineProps({ file: { type: Object, default: null } });
defineEmits(["close", "error"]);
const playerEl = ref(null);
const videoEl = ref(null);
watch(() => props.file, () => nextTick(() => {
  if (playerEl.value) playerEl.value.scrollIntoView({ behavior: "smooth", block: "nearest" });
  if (videoEl.value) videoEl.value.play().catch(() => {});
}));
function fmtDate(timestamp) { return new Date(timestamp * 1000).toLocaleString(); }
</script>
