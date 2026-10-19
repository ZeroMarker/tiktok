// material.js — 集中注册用到的 @material/web 组件。
//
// 裸模块名由 webui/index.html 的静态 import map 映射到 ./vendor/*（纯本地，无 CDN）。
// 一条 import 汇总，避免每个组件各自重复注册；浏览器按模块缓存，只加载一次。
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/button/text-button.js";
import "@material/web/checkbox/checkbox.js";
import "@material/web/chips/filter-chip.js";
import "@material/web/dialog/dialog.js";
import "@material/web/divider/divider.js";
import "@material/web/iconbutton/icon-button.js";
import "@material/web/list/list.js";
import "@material/web/list/list-item.js";
import "@material/web/progress/circular-progress.js";
import "@material/web/progress/linear-progress.js";
import "@material/web/select/outlined-select.js";
import "@material/web/select/select-option.js";
import "@material/web/textfield/outlined-text-field.js";
