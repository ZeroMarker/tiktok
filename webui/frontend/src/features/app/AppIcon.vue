<template>
  <svg class="app-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path :d="paths[name] || paths.circle" />
  </svg>
</template>

<script setup>
defineProps({ name: { type: String, default: "circle" } });

const paths = {
  overview: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z",
  tasks: "M4 5h2v2H4V5Zm4 0h12v2H8V5ZM4 11h2v2H4v-2Zm4 0h12v2H8v-2ZM4 17h2v2H4v-2Zm4 0h12v2H8v-2Z",
  library: "M4 4h16v16H4V4Zm2 2v12h12V6H6Zm2 2h8v2H8V8Zm0 4h8v4H8v-4Z",
  add: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z",
  record: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 6a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z",
  distribution: "M4 19h4V9H4v10Zm6 0h4V5h-4v14Zm6 0h4v-7h-4v7Z",
  terminal: "m4 6 5 5-5 5 1.4 1.4L11.8 11 5.4 4.6 4 6Zm8 10h8v2h-8v-2Z",
  storage: "M4 5c0-1.1 3.6-2 8-2s8 .9 8 2-3.6 2-8 2-8-.9-8-2Zm0 3.1c1.8.9 4.8 1.4 8 1.4s6.2-.5 8-1.4V12c0 1.1-3.6 2-8 2s-8-.9-8-2V8.1Zm0 7c1.8.9 4.8 1.4 8 1.4s6.2-.5 8-1.4V19c0 1.1-3.6 2-8 2s-8-.9-8-2v-3.9Z",
  activity: "M3 13h4l2-6 4 12 2-6h6v-2h-7l-1 3-4-12-3 9H3v2Z",
  circle: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Z",
};
</script>
