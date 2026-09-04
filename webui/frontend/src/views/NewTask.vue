<template>
  <div class="new-task">
    <section class="panel create-panel">
      <div class="panel-title">
        <div class="title-wrap">
          <span class="section-icon"><AppIcon name="add" /></span>
          <div><h2>新建录制</h2><span class="panel-kicker">选择平台并输入直播间信息</span></div>
        </div>
      </div>
      <TaskCreationForm />
    </section>
  </div>
</template>
<script setup>
import TaskCreationForm from "../features/task-creation/TaskCreationForm.vue";
import AppIcon from "../features/app/AppIcon.vue";
</script>
