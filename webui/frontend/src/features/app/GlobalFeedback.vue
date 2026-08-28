<template>
  <div class="modal" :class="{ hidden: !ui.confirm.visible }" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-text" @click.self="closeConfirm">
    <div class="modal-box">
      <h3 id="modal-title">{{ ui.confirm.title }}</h3><p id="modal-text">{{ ui.confirm.text }}</p>
      <div class="modal-actions"><button class="secondary" type="button" @click="closeConfirm">取消</button><button type="button" :class="ui.confirm.danger ? 'danger' : 'secondary'" @click="confirm">{{ ui.confirm.okText }}</button></div>
    </div>
  </div>
  <div class="toast" v-show="ui.toast" role="status" aria-live="polite">{{ ui.toast }}</div>
</template>
<script setup>
import { onMounted, onUnmounted } from "vue";
import { ui, closeConfirm } from "../../ui.js";

function confirm() { const callback = ui.confirm.cb; closeConfirm(); if (callback) callback(); }
function onKeydown(event) { if (event.key === "Escape" && ui.confirm.visible) closeConfirm(); }
onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>
