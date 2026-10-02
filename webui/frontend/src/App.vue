<template>
  <div class="shell" :class="{ offline: appState.offline, degraded: appState.degraded }">
    <AppHeader />
    <a class="skip-link" href="#page-content" @click.prevent="focusContent">跳转到页面内容</a>
    <div class="workspace">
      <AppNav />
      <main id="page-content" class="page-content" tabindex="-1">
        <ConnectionBanner />
        <div v-if="appState.busy && !appState.loadedOnce" class="loading-state" role="status">正在同步直播任务与录制文件…</div>
        <component v-else :is="viewComponent" :key="viewKey" :unit="route.unit" />
      </main>
    </div>
    <GlobalFeedback />
  </div>
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

function focusContent() { document.getElementById("page-content")?.focus(); }

const views = { overview: Overview, tasks: Tasks, task: TaskDetail, library: Library, new: NewTask };
const viewComponent = computed(() => views[route.value.name] || Overview);
const viewKey = computed(() => route.value.name + (route.value.unit || ""));
</script>
