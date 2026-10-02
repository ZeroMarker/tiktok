<template>
  <nav class="nav" aria-label="主导航">
    <p class="nav-label">工作空间</p>
    <button v-for="item in items" :key="item.path" class="nav-item" :class="{ active: isActive(item), primary: item.name === 'new' }" type="button" :aria-current="isActive(item) ? 'page' : undefined" @click="navigate(item.path)"><AppIcon :name="item.icon" /><span>{{ item.label }}</span><span v-if="isActive(item)" class="nav-indicator" aria-hidden="true"></span></button>
    <div class="nav-note"><AppIcon name="record" /><span>跨平台录制<br><small>统一管理每一场直播</small></span></div>
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
