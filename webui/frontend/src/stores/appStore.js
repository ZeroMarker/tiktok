import { reactive } from "vue";

export const appState = reactive({
  offline: false,
  degraded: false,
  busy: false,
  errors: { jobs: "", overview: "", files: "" },
  loadedOnce: false,
  lastSynced: null,
  installPrompt: null,
});
