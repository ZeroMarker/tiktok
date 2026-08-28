<template>
  <nav class="nav" aria-label="主导航">
    <button v-for="item in items" :key="item.path" class="nav-item" :class="{ active: isActive(item) }" type="button" :aria-current="isActive(item) ? 'page' : undefined" @click="navigate(item.path)">{{ item.label }}</button>
  </nav>
</template>
<script setup>
import { route, navigate } from "../../router.js";

const items = [
  { path: "/", label: "概览", name: "overview" },
  { path: "/tasks", label: "任务", name: "tasks" },
  { path: "/library", label: "录制文件", name: "library" },
  { path: "/new", label: "新建任务", name: "new" },
];
function isActive(item) { return route.value.name === item.name || (item.name === "tasks" && route.value.name === "task"); }
</script>
