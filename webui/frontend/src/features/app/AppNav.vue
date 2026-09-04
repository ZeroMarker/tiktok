<template>
  <nav class="nav" aria-label="主导航">
    <button v-for="item in items" :key="item.path" class="nav-item" :class="{ active: isActive(item) }" type="button" :aria-current="isActive(item) ? 'page' : undefined" @click="navigate(item.path)"><AppIcon :name="item.icon" />{{ item.label }}</button>
  </nav>
</template>
<script setup>
import { route, navigate } from "../../router.js";
import AppIcon from "./AppIcon.vue";

const items = [
  { path: "/", label: "概览", name: "overview", icon: "overview" },
  { path: "/tasks", label: "任务", name: "tasks", icon: "tasks" },
  { path: "/library", label: "录制文件", name: "library", icon: "library" },
  { path: "/new", label: "新建任务", name: "new", icon: "add" },
];
function isActive(item) { return route.value.name === item.name || (item.name === "tasks" && route.value.name === "task"); }
</script>
