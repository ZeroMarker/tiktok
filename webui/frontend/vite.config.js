import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteSingleFile } from "vite-plugin-singlefile";

// 构建为单个自包含 index.html（Vue 运行时 + 组件 + CSS 全部内联）：
// 便于现有 python http.server 直接服务，且无需构建期写盘（配合 ProtectSystem=strict）。
export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  base: "./",
  build: {
    target: "es2018",
  },
});
