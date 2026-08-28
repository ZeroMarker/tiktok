<template>
  <div class="stat">
    <div class="stat-top"><span class="stat-label">{{ label }}</span><span class="stat-icon">{{ icon }}</span></div>
    <b :style="bar != null ? { color: tone } : {}">{{ value }}</b>
    <span class="stat-note">{{ note }}</span>
    <div v-if="bar != null" class="bar" aria-hidden="true"><i :style="{ width: clampBar + '%', background: tone || 'linear-gradient(90deg,var(--brand),var(--blue))' }"></i></div>
  </div>
</template>
<script setup>
import { computed } from "vue";
const props = defineProps({ label: String, icon: String, value: [String, Number], note: String, bar: { type: Number, default: null } });
const tone = computed(() => props.bar >= 90 ? "var(--red)" : props.bar >= 75 ? "var(--warn)" : "");
const clampBar = computed(() => Math.min(100, Math.max(0, props.bar ?? 0)));
</script>
