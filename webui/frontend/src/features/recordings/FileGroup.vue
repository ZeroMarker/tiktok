<template>
  <div class="fgroup" :class="{ open }">
    <button class="fgroup-head" type="button" :aria-expanded="open" @click="$emit('toggle', group.dir)">
      <span class="chevron">▶</span><span>{{ group.name }}</span><span class="count">{{ group.files.length }} 个文件</span>
    </button>
    <div class="fgroup-body">
      <FileRow v-for="file in group.files" :key="file.path" :file="file" :active="activePath === file.path" :pending="pendingPath === file.path" @play="$emit('play', file)" @delete="$emit('delete', file)" />
    </div>
  </div>
</template>
<script setup>
import FileRow from "./FileRow.vue";

defineProps({ group: { type: Object, required: true }, open: Boolean, activePath: String, pendingPath: String });
defineEmits(["toggle", "play", "delete"]);
</script>
