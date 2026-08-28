<template>
  <div id="player" class="player-overlay" :class="{ hidden: !ui.player.open }" role="dialog" aria-modal="true" aria-label="录制文件播放">
    <div class="player-box">
      <div class="player-head">
        <span class="player-title">{{ ui.player.name }}</span>
        <div class="player-actions">
          <a :href="ui.player.src" download="playback.mp4">下载</a>
          <button class="secondary player-close" @click="closePlayer">关闭</button>
        </div>
      </div>
      <video ref="videoEl" controls playsinline preload="metadata" :src="ui.player.src"></video>
    </div>
  </div>
</template>
<script setup>
import { ref, watch, onUnmounted } from "vue";
import { ui, closePlayer } from "../ui.js";

const videoEl = ref(null);

watch(
  () => ui.player.open,
  (open) => {
    if (open) {
      document.body.classList.add("player-open");
      nextPlay();
    } else {
      document.body.classList.remove("player-open");
      const v = videoEl.value;
      if (v) {
        v.pause();
        v.removeAttribute("src");
        v.load();
      }
    }
  }
);

function nextPlay() {
  const v = videoEl.value;
  if (!v) return;
  v.load();
  v.play().catch(() => {});
}

function onKey(e) {
  if (e.key === "Escape" && ui.player.open) closePlayer();
}
document.addEventListener("keydown", onKey);
onUnmounted(() => document.removeEventListener("keydown", onKey));
</script>
