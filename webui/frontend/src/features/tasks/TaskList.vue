<template>
  <div class="jobs">
    <TaskCard v-for="job in jobs" :key="job.unit" :job="job" :selected="job.unit === taskState.selectedUnit" @open="$emit('open', job)" @restart="$emit('restart', job)" @stop="$emit('stop', job)" />
    <div v-if="!jobs.length" class="empty">
      <strong>{{ filtered ? "没有符合条件的任务" : "还没有录制任务" }}</strong>
      <span>{{ filtered ? "请调整搜索关键词或筛选条件" : "创建一个任务后，它会显示在这里" }}</span>
      <button v-if="!filtered" class="secondary" type="button" @click="navigate('/new')">新建任务</button>
    </div>
  </div>
</template>
<script setup>
import TaskCard from "./TaskCard.vue";
import { taskState } from "../../stores/taskStore.js";
import { navigate } from "../../router.js";

defineProps({ jobs: { type: Array, default: () => [] }, filtered: Boolean });
defineEmits(["open", "restart", "stop"]);
</script>
