<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Reading, School, Lock, User } from '@element-plus/icons-vue'
import { login } from '../api'

const emit = defineEmits<{ authenticated: [] }>()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
async function submit() {
  if (!username.value.trim() || !password.value) { error.value = '请输入账号和密码'; return }
  busy.value = true
  error.value = ''
  try { await login(username.value.trim(), password.value); emit('authenticated') }
  catch (e) { error.value = e instanceof Error ? e.message : '登录失败，请稍后重试' }
  finally { busy.value = false }
}
function demo(value: string) { username.value = value; password.value = 'Demo@2026'; ElMessage.info('已填入演示账号，请点击登录') }
</script>

<template>
  <main class="login-page">
    <section class="login-story">
      <div class="brand"><el-icon><Reading /></el-icon><span>知序 <small>ACADEMIC SERVICES</small></span></div>
      <div class="story-body"><span class="eyebrow">高校教务 · 缓考与重修服务</span><h1>让每一段学习，<br>都有序前行。</h1><p>申请有依据，审核有记录，进度有回应。<br>连接学生、教师与教务，让办理更清晰。</p><div class="story-process"><span>在线申请</span><i></i><span>分级审核</span><i></i><span>全程可查</span></div></div>
      <div class="story-bottom"><el-icon><School /></el-icon> 学生课程缓考与重修管理系统 <span>毕业设计 · 演示环境</span></div>
      <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
    </section>
    <section class="login-panel">
      <div class="login-card"><span class="eyebrow">WELCOME BACK</span><h2>欢迎登录</h2><p class="muted">使用教务账号，进入你的办事空间。</p>
        <form @submit.prevent="submit">
          <label for="username">账号</label><el-input id="username" v-model="username" :prefix-icon="User" autocomplete="username" placeholder="请输入学号 / 工号" size="large" maxlength="50" />
          <label for="password">密码</label><el-input id="password" v-model="password" :prefix-icon="Lock" type="password" autocomplete="current-password" placeholder="请输入密码" show-password size="large" />
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <el-button type="primary" native-type="submit" size="large" :loading="busy" class="login-button">登录办事空间</el-button>
        </form>
        <div class="demo-box"><b>快速体验</b><p>虚构数据 · 仅用于本地验收</p><div class="demo-buttons"><el-button @click="demo('20240001')">学生</el-button><el-button @click="demo('teacher01')">教师</el-button><el-button @click="demo('dept01')">院系教务</el-button><el-button @click="demo('admin')">校教务</el-button></div></div>
        <p class="login-note">账号问题请联系学校教务人员。</p>
      </div>
    </section>
  </main>
</template>
