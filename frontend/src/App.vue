<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Reading, House, Tickets, DocumentAdd, Notebook, Bell, SwitchButton, Plus, Refresh, CircleCheck, Timer, Document, School } from '@element-plus/icons-vue'
import LoginView from './components/LoginView.vue'
import ApplicationForm from './components/ApplicationForm.vue'
import ApplicationDetail from './components/ApplicationDetail.vue'
import { ApiError, logout, request } from './api'
import type { Actor, Application, Course, Detail, Notice, Page } from './types'
import { formatTime, roleNames, roleStages, statusNames } from './types'

type View = 'home' | 'applications' | 'new' | 'courses' | 'notifications'
const actor = ref<Actor | null>(null)
const initializing = ref(true)
const view = ref<View>('home')
const applications = ref<Application[]>([])
const courses = ref<Course[]>([])
const notifications = ref<Notice[]>([])
const total = ref(0)
const page = ref(1)
const pendingOnly = ref(false)
const busy = ref(false)
const loadError = ref('')
const detail = ref<Detail | null>(null)
const drawerOpen = ref(false)
const isStudent = computed(() => actor.value?.role === 'STUDENT')
const unread = computed(() => notifications.value.filter(n => !n.isRead).length)
const pending = computed(() => applications.value.filter(a => a.status.endsWith('_REVIEW')).length)
const approved = computed(() => applications.value.filter(a => a.status === 'APPROVED').length)
const nav = computed(() => [
  { key: 'home' as View, label: '工作台', icon: House },
  { key: 'applications' as View, label: isStudent.value ? '我的申请' : '申请审核', icon: Tickets },
  ...(isStudent.value ? [{ key: 'courses' as View, label: '我的课程', icon: Notebook }] : []),
  { key: 'notifications' as View, label: '消息中心', icon: Bell },
])
const title = computed(() => view.value === 'new' ? '新建缓考申请' : nav.value.find(n => n.key === view.value)?.label ?? '工作台')
async function authenticated() {
  try { actor.value = await request<Actor>('/auth/me'); view.value = 'home'; page.value = 1; pendingOnly.value = false; await refresh() }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '身份加载失败') }
}
async function refresh() {
  if (!actor.value) return
  busy.value = true; loadError.value = ''
  try {
    const [apps, notices, rows] = await Promise.all([
      request<Page<Application>>(`/deferrals?page=${page.value}&size=20&pendingOnly=${pendingOnly.value}`),
      request<Page<Notice>>('/notifications?size=100'),
      isStudent.value ? request<Course[]>('/courses') : Promise.resolve([] as Course[]),
    ])
    applications.value = apps.items; total.value = apps.total; notifications.value = notices.items; courses.value = rows
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) { actor.value = null; ElMessage.info('会话已过期，请重新登录') }
    else loadError.value = e instanceof Error ? e.message : '数据加载失败'
  } finally { busy.value = false }
}
async function signOut() {
  try { await logout(); actor.value = null; applications.value = []; courses.value = []; notifications.value = []; detail.value = null; drawerOpen.value = false }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '退出失败') }
}
function navigate(next: View) { view.value = next; window.scrollTo({ top: 0, behavior: 'instant' }) }
async function openDetail(id: number) {
  try { detail.value = await request<Detail>(`/deferrals/${id}`); drawerOpen.value = true }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '详情加载失败') }
}
async function submitted(result: Detail) { view.value = 'applications'; page.value = 1; pendingOnly.value = false; await refresh(); detail.value = result; drawerOpen.value = true }
async function reviewed(result: Detail) { detail.value = result; await refresh() }
async function readNotice(notice: Notice) {
  try { await request(`/notifications/${notice.id}/read`, { method: 'POST' }); notice.isRead = true; if (notice.applicationId) await openDetail(notice.applicationId) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '消息更新失败') }
}
async function filterChanged() { page.value = 1; await refresh() }
onMounted(async () => {
  try { actor.value = await request<Actor>('/auth/me'); await refresh() }
  catch (e) { if (!(e instanceof ApiError && e.status === 401)) ElMessage.error('无法连接服务，请确认后端已启动') }
  finally { initializing.value = false }
})
</script>

<template>
  <div v-if="initializing" class="initializing" role="status">正在连接教务服务…</div>
  <LoginView v-else-if="!actor" @authenticated="authenticated" />
  <div v-else class="app-shell">
    <aside class="sidebar"><div class="brand"><el-icon><Reading /></el-icon><span>知序 <small>教务办事空间</small></span></div><p class="sidebar-caption">ACADEMIC SERVICES</p><nav aria-label="主导航"><button v-for="item in nav" :key="item.key" :class="{ active: view === item.key || (view === 'new' && item.key === 'applications') }" @click="navigate(item.key)"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}<span v-if="item.key === 'notifications' && unread" class="nav-count">{{ unread }}</span></button></nav><div class="sidebar-guide"><el-icon><School /></el-icon><b>每一程，都有回应</b><p>清晰的流程，让学习安排<br>更从容。</p><span>缓考与重修管理系统</span></div><div class="sidebar-bottom">毕业设计 · 本地演示 <span>v0.2</span></div></aside>
    <div class="main-shell"><header class="topbar"><div class="breadcrumb">教务服务 <span>/</span><b>{{ title }}</b></div><div class="topbar-actions"><button class="bell-button" aria-label="打开消息中心" @click="navigate('notifications')"><el-icon><Bell /></el-icon><span v-if="unread" class="bell-dot"></span></button><div class="user-avatar">{{ actor.displayName.slice(0, 1) }}</div><div class="user-info"><b>{{ actor.displayName }}</b><span>{{ roleNames[actor.role] }} · {{ actor.username }}</span></div><el-button text :icon="SwitchButton" @click="signOut">退出</el-button></div></header>
      <main class="workspace" v-loading="busy"><div class="page-heading"><div><span class="eyebrow">{{ actor.departmentName }}</span><h1>{{ view === 'home' ? `${actor.displayName}，你好` : title }}</h1><p>{{ view === 'home' ? '在这里查看办理进度，安排接下来的学习。' : view === 'new' ? '如实填写申请信息，材料将仅供授权审核人员查阅。' : view === 'applications' ? isStudent ? '每一步进度，清晰可查。' : '核对申请与材料，按当前节点完成审核。' : view === 'courses' ? '查看个人开课信息、考试安排与成绩。' : '申请进度与待办提醒，都在这里。' }}</p></div><el-button v-if="isStudent && view !== 'new'" type="primary" size="large" :icon="Plus" @click="navigate('new')">新建缓考申请</el-button><el-button v-else-if="view !== 'new'" :icon="Refresh" @click="refresh">刷新数据</el-button></div>
        <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" class="load-error"><el-button text @click="refresh">重新加载</el-button></el-alert>
        <template v-if="view === 'home'"><section class="welcome-banner"><div><span class="banner-label">{{ isStudent ? '你的学业，妥善安排' : '有序审核，及时回应' }}</span><h2>{{ isStudent ? '申请少一些等待，学习多一份从容。' : '让每一份申请，都有清晰的下一步。' }}</h2><p>{{ isStudent ? '缓考申请、进度查询与通知，一处办理。' : '待办按角色与院系分配，处理记录全程留存。' }}</p><button @click="navigate('applications')">{{ isStudent ? '查看我的申请' : '进入申请审核' }}</button></div><div class="banner-art" aria-hidden="true"><div class="art-card"><el-icon><Document /></el-icon><i></i><i></i><span><el-icon><CircleCheck /></el-icon> 流程有序 · 全程可查</span></div><div class="art-ring"></div></div></section>
          <div class="stat-grid"><section class="stat-card"><div><span>{{ pendingOnly ? '筛选后申请' : '申请记录' }}</span><strong>{{ total }}<small>份</small></strong></div><el-icon class="stat-icon sage"><Tickets /></el-icon></section><section class="stat-card"><div><span>本页处理中</span><strong>{{ pending }}<small>份</small></strong></div><el-icon class="stat-icon amber"><Timer /></el-icon></section><section class="stat-card"><div><span>本页已通过</span><strong>{{ approved }}<small>份</small></strong></div><el-icon class="stat-icon green"><CircleCheck /></el-icon></section><section class="stat-card"><div><span>最近100条未读消息</span><strong>{{ unread }}<small>条</small></strong></div><el-icon class="stat-icon blue"><Bell /></el-icon></section></div>
          <div class="home-grid"><section class="panel"><div class="panel-title"><h3>{{ isStudent ? '最近申请' : '最近申请记录' }}</h3><button @click="navigate('applications')">查看全部</button></div><div v-if="applications.length" class="recent-list"><button v-for="item in applications.slice(0, 5)" :key="item.id" @click="openDetail(item.id)"><span class="course-icon"><Document /></span><span class="recent-name"><b>{{ item.courseName }}</b><small>缓考申请 · #{{ item.id }} · {{ formatTime(item.createdAt) }}</small></span><span class="status-pill" :class="item.status.toLowerCase()">{{ statusNames[item.status] }}</span></button></div><el-empty v-else description="暂时还没有申请记录" :image-size="88"><el-button v-if="isStudent" type="primary" plain @click="navigate('new')">发起第一份申请</el-button><span v-else class="muted">新的申请会出现在这里</span></el-empty></section><aside class="panel process-panel"><div class="panel-title"><h3>缓考办理指南</h3><el-icon><DocumentAdd /></el-icon></div><ol class="process-list"><li><span>1</span><div><b>提交申请</b><p>选择课程，填写理由与材料</p></div></li><li><span>2</span><div><b>三级审核</b><p>任课教师 → 院系 → 校教务</p></div></li><li><span>3</span><div><b>关注办理结果</b><p>审核通过后等待学校安排</p></div></li></ol><p class="process-note">当前开放缓考申请与审核。重修选课、成绩归档将在后续阶段开放。</p></aside></div>
        </template>
        <section v-else-if="view === 'applications'" class="panel"><div class="panel-title"><h3>{{ isStudent ? '我的缓考申请' : '缓考申请审核' }} <span class="count-label">{{ total }}</span></h3><div class="table-controls"><el-checkbox v-if="!isStudent" v-model="pendingOnly" @change="filterChanged">仅看待我审核</el-checkbox><el-button text :icon="Refresh" @click="refresh">刷新</el-button></div></div><el-table :data="applications" empty-text="暂无申请记录" @row-click="(row: Application) => openDetail(row.id)"><el-table-column label="申请编号" width="110"><template #default="{ row }">#{{ row.id }}</template></el-table-column><el-table-column prop="courseName" label="课程" min-width="150" /><el-table-column v-if="!isStudent" prop="studentName" label="学生" width="110" /><el-table-column prop="term" label="学期" min-width="210" /><el-table-column label="提交时间" width="150"><template #default="{ row }">{{ formatTime(row.createdAt) }}</template></el-table-column><el-table-column label="状态" width="145"><template #default="{ row }"><span class="status-pill" :class="row.status.toLowerCase()">{{ statusNames[row.status as keyof typeof statusNames] }}</span></template></el-table-column><el-table-column label="操作" width="115"><template #default="{ row }"><el-button link type="primary" @click.stop="openDetail(row.id)">{{ !isStudent && roleStages[actor.role] === row.status ? '处理审核' : '查看详情' }}</el-button></template></el-table-column></el-table><div class="pagination"><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="refresh" /></div></section>
        <ApplicationForm v-else-if="view === 'new' && isStudent" :courses="courses" @submitted="submitted" @cancel="navigate('applications')" />
        <section v-else-if="view === 'courses' && isStudent" class="panel"><div class="panel-title"><h3>个人课程与成绩</h3><span>{{ courses.length }} 门课程</span></div><el-table :data="courses" empty-text="暂无课程"><el-table-column prop="courseCode" label="课程代码" width="120" /><el-table-column prop="courseName" label="课程名称" min-width="160" /><el-table-column prop="credits" label="学分" width="90" /><el-table-column prop="teacherName" label="任课教师" width="120" /><el-table-column prop="term" label="学期" min-width="230" /><el-table-column label="考试时间（北京时间）" width="190"><template #default="{ row }">{{ formatTime(row.examAt) }}</template></el-table-column><el-table-column label="成绩" width="100"><template #default="{ row }"><span :class="{ 'score-failed': row.score !== null && row.score < 60 }">{{ row.score ?? '未出分' }}</span></template></el-table-column></el-table></section>
        <section v-else-if="view === 'notifications'" class="panel"><div class="panel-title"><h3>站内通知</h3><span>显示最近100条 · {{ unread }} 条未读</span></div><div v-if="notifications.length" class="notification-list"><button v-for="notice in notifications" :key="notice.id" :class="{ unread: !notice.isRead }" @click="readNotice(notice)"><el-icon><Bell /></el-icon><span><b>{{ notice.title }} <small v-if="!notice.isRead">未读</small></b><p>{{ notice.content }}</p><time>{{ formatTime(notice.createdAt) }}</time></span><span class="notice-action">{{ notice.applicationId ? '查看申请' : notice.isRead ? '已读' : '标为已读' }}</span></button></div><el-empty v-else description="暂时没有新的消息" /></section>
        <footer class="workspace-footer">知序 · 高校学生课程缓考与重修管理系统 <span>信息有据，办理有序。</span></footer>
      </main></div>
    <el-drawer v-model="drawerOpen" title="申请详情" size="min(680px, 100vw)" destroy-on-close><ApplicationDetail v-if="detail" :key="detail.application.id" :detail="detail" :actor="actor" @reviewed="reviewed" /></el-drawer>
  </div>
</template>
