<template>
  <main class="shell" :class="{ offline: appState.offline, degraded: appState.degraded }">
    <AppHeader />
    <AppNav />
    <ConnectionBanner />
    <component :is="viewComponent" :key="viewKey" :unit="route.unit" />
    <GlobalFeedback />
  </main>
</template>
<script setup>
import { computed } from "vue";
import Overview from "./views/Overview.vue";
import Tasks from "./views/Tasks.vue";
import TaskDetail from "./views/TaskDetail.vue";
import Library from "./views/Library.vue";
import NewTask from "./views/NewTask.vue";
import AppHeader from "./features/app/AppHeader.vue";
import AppNav from "./features/app/AppNav.vue";
import ConnectionBanner from "./features/app/ConnectionBanner.vue";
import GlobalFeedback from "./features/app/GlobalFeedback.vue";
import { appState } from "./stores/appStore.js";
import { route } from "./router.js";

const views = { overview: Overview, tasks: Tasks, task: TaskDetail, library: Library, new: NewTask };
const viewComponent = computed(() => views[route.value.name] || Overview);
const viewKey = computed(() => route.value.name + (route.value.unit || ""));
</script>
<style scoped>
.nav { display: flex; gap: 7px; flex-wrap: wrap; margin: 0 0 12px; }
.nav-item { min-height: 36px; padding: 7px 14px; font-size: 12px; border-radius: 999px; background: #0b1615; border: 1px solid var(--line); color: var(--muted); cursor: pointer; }
.nav-item:hover { border-color: var(--line-strong); color: var(--text); }
.nav-item.active { background: rgba(88, 224, 173, 0.14); border-color: rgba(88, 224, 173, 0.5); color: var(--brand); }
@media (max-width: 680px) { .nav-item { flex: 1; text-align: center; } }
</style>
