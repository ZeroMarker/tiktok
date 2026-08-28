// router.js — 极简 hash 路由：#/、#/tasks、#/tasks/:unit、#/library、#/new。
import { ref } from "vue";

function parse() {
  const h = (location.hash || "").replace(/^#/, "");
  const parts = h.split("/").filter(Boolean);
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

export const route = ref(parse());

export function navigate(path) {
  if ((location.hash || "") === "#" + path) return;
  location.hash = path;
}

window.addEventListener("hashchange", () => {
  route.value = parse();
});
