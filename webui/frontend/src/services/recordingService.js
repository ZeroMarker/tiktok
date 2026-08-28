import { api } from "../api.js";

export const recordingService = {
  list: ({ query = "", limit = 80, offset = 0 } = {}) =>
    api("api/files?q=" + encodeURIComponent(query) + "&limit=" + limit + "&offset=" + Math.max(0, offset)),
  delete: (path) => api("api/delete", { method: "POST", body: JSON.stringify({ path }) }),
};
