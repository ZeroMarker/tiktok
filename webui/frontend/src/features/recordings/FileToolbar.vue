<template>
  <div class="log-tools">
    <input v-model="localQuery" class="file-search" placeholder="搜索文件名或目录" aria-label="搜索文件">
    <button class="mini secondary" type="button" @click="$emit('expand-all', true)">全部展开</button>
    <button class="mini secondary" type="button" @click="$emit('expand-all', false)">全部收起</button>
  </div>
</template>
<script setup>
import { onUnmounted, ref, watch } from "vue";

const props = defineProps({ query: { type: String, default: "" } });
const emit = defineEmits(["search", "expand-all"]);
const localQuery = ref(props.query);
let timer = null;
watch(() => props.query, (value) => { localQuery.value = value; });
watch(localQuery, (value) => {
  clearTimeout(timer);
  timer = setTimeout(() => emit("search", value), 250);
});
onUnmounted(() => clearTimeout(timer));
</script>
