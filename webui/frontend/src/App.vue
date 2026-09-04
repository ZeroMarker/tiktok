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
