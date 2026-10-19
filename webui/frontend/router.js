// router.js — 极简 hash 路由：#/、#/tasks、#/tasks/:unit、#/library、#/new。
import { createStore } from "./stores/store.js";

function parse() {
  const hash = (location.hash || "").replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts.length === 0) return { name: "overview" };
  if (parts[0] === "tasks") {
    if (parts[1]) {
      try {
        return { name: "task", unit: decodeURIComponent(parts[1]) };
      } catch {
        return { name: "tasks" };
      }
    }
    return { name: "tasks" };
  }
  if (parts[0] === "library") return { name: "library" };
  if (parts[0] === "new") return { name: "new" };
  return { name: "overview" };
}

export const route = createStore(parse());

export function navigate(path) {
  if ((location.hash || "") === "#" + path) return;
  location.hash = path;
}

window.addEventListener("hashchange", () => {
  const next = parse();
  route.name = next.name;
  if (next.unit) route.unit = next.unit;
  else delete route.unit;
});
