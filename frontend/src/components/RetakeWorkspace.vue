<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '../api'
import type { Actor, Page } from '../types'
import { formatTime } from '../types'
import type { RetakeApplication, RetakeDetail as Detail, RetakeMeta, TimetableEntry } from '../retake-types'
import { retakeStatusNames, slotLabel } from '../retake-types'
import RetakeDetail from './RetakeDetail.vue'
import RetakeClasses from './RetakeClasses.vue'

const props = defineProps<{ actor: Actor; focusId: number | null }>()
const emit = defineEmits<{ changed: [] }>()
const meta = ref<RetakeMeta>({ terms: [], eligibleCourses: [], courses: [], teachers: [] })
const tab = ref(props.actor.role === 'TEACHER' ? 'classes' : 'applications')
const rows = ref<RetakeApplication[]>([])
const approvedApplications = ref<RetakeApplication[]>([])
const total = ref(0)
const page = ref(1)
const pendingOnly = ref(false)
const busy = ref(false)
const error = ref('')
const detail = ref<Detail | null>(null)
const drawerOpen = ref(false)
const formOpen = ref(false)
const formEnrollmentId = ref<number>()
const formTermId = ref<number>()
const reason = ref('')
const formError = ref('')
const submitting = ref(false)
const selectedApplicationId = ref<number | null>(null)
const timetable = ref<TimetableEntry[]>([])
const timetableTerm = ref<number>()
const timetableBusy = ref(false)
const timetableError = ref('')
const isStudent = computed(() => props.actor.role === 'STUDENT')
const isReviewer = computed(() => ['DEPARTMENT_ADMIN', 'SCHOOL_ADMIN'].includes(props.actor.role))
const pendingStage = computed(() => props.actor.role === 'DEPARTMENT_ADMIN' ? 'DEPARTMENT_REVIEW' : props.actor.role === 'SCHOOL_ADMIN' ? 'SCHOOL_REVIEW' : null)
async function loadApplications() {
  const data = await request<Page<RetakeApplication>>(`/retakes?page=${page.value}&size=20&pendingOnly=${pendingOnly.value}`)
  rows.value = data.items; total.value = data.total
  if (isStudent.value) {
    const all = await request<Page<RetakeApplication>>('/retakes?size=100')
    approvedApplications.value = all.items.filter(row => row.status === 'APPROVED')
  }
}
async function refresh() {
  busy.value = true; error.value = ''
  try {
    const data = await request<RetakeMeta>('/retake-meta'); meta.value = data
    formEnrollmentId.value ??= data.eligibleCourses[0]?.id
    formTermId.value ??= data.terms[0]?.id
    timetableTerm.value ??= data.terms[0]?.id
    await loadApplications()
  } catch (e) { error.value = e instanceof Error ? e.message : '重修数据加载失败' }
  finally { busy.value = false }
}
async function filterChanged() { page.value = 1; await refresh() }
async function openDetail(id: number) {
  try { detail.value = await request<Detail>(`/retakes/${id}`); drawerOpen.value = true }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '详情加载失败') }
}
function startApplication() { formError.value = ''; formOpen.value = true }
async function submit() {
  formError.value = ''
  if (!formEnrollmentId.value || !formTermId.value || reason.value.trim().length < 10) { formError.value = '请选择不及格课程和重修学期，并填写至少10字理由'; return }
  submitting.value = true
  try {
    const result = await request<Detail>('/retakes', { method: 'POST', body: JSON.stringify({ enrollmentId: formEnrollmentId.value, termId: formTermId.value, reason: reason.value.trim() }) })
    formOpen.value = false; reason.value = ''; page.value = 1; pendingOnly.value = false; tab.value = 'applications'
    await refresh(); detail.value = result; drawerOpen.value = true; emit('changed'); ElMessage.success('重修申请已进入院系审核')
  } catch (e) { formError.value = e instanceof Error ? e.message : '提交失败' }
  finally { submitting.value = false }
}
async function changed() { await refresh(); emit('changed') }
async function reviewed(value: Detail) { detail.value = value; await changed() }
function chooseClass(id: number) {
  const application = rows.value.find(row => row.id === id) ?? (detail.value?.application.id === id ? detail.value.application : undefined)
  if (application && !approvedApplications.value.some(row => row.id === id)) approvedApplications.value.push(application)
  selectedApplicationId.value = id; drawerOpen.value = false; tab.value = 'classes'
}
async function loadTimetable() {
  if (!timetableTerm.value) return
  timetableBusy.value = true; timetableError.value = ''
  try { timetable.value = await request<TimetableEntry[]>(`/timetable?termId=${timetableTerm.value}`) }
  catch (e) { timetableError.value = e instanceof Error ? e.message : '课表加载失败' }
  finally { timetableBusy.value = false }
}
watch(tab, value => { if (value === 'timetable') void loadTimetable() })
watch(() => props.focusId, id => { if (id) void openDetail(id) })
onMounted(async () => { await refresh(); if (props.focusId) await openDetail(props.focusId) })
</script>
<template>
  <div class="m2-workspace" v-loading="busy"><div class="m2-intro"><div><span class="eyebrow">RETAKE SERVICES</span><h2>{{ isStudent ? '重新出发，有序修读。' : actor.role === 'TEACHER' ? '重修教学，名单清晰。' : '申请与开班，一处协同。' }}</h2><p>{{ isStudent ? '申请通过后，选择适合你的重修班级；系统会检查课程冲突与名额。' : '重修申请按院系、校教务两级流转，选课记录与教学名单同步。' }}</p></div><el-button v-if="isStudent" type="primary" size="large" @click="startApplication">新建重修申请</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon><el-button text @click="refresh">重新加载</el-button></el-alert>
    <el-tabs v-model="tab" class="m2-tabs"><el-tab-pane v-if="actor.role !== 'TEACHER'" :label="isStudent ? '我的重修申请' : '重修申请审核'" name="applications" /><el-tab-pane :label="actor.role === 'SCHOOL_ADMIN' ? '开班管理' : actor.role === 'TEACHER' ? '我的重修班' : '重修班级'" name="classes" /><el-tab-pane v-if="isStudent" label="我的课表" name="timetable" /></el-tabs>
    <section v-if="tab === 'applications'" class="panel"><div class="panel-title"><h3>重修申请 <span class="count-label">{{ total }}</span></h3><div class="table-controls"><el-checkbox v-if="isReviewer" v-model="pendingOnly" @change="filterChanged">仅看待我审核</el-checkbox><el-button text @click="refresh">刷新</el-button></div></div><el-table :data="rows" empty-text="暂无重修申请"><el-table-column label="编号" width="90"><template #default="{ row }">#{{ row.id }}</template></el-table-column><el-table-column prop="courseName" label="课程" min-width="150" /><el-table-column v-if="!isStudent" prop="studentName" label="学生" width="105" /><el-table-column label="原成绩" width="90"><template #default="{ row }">{{ row.score }} 分</template></el-table-column><el-table-column prop="term" label="重修学期" min-width="235" /><el-table-column label="状态" width="140"><template #default="{ row }"><span class="status-pill" :class="row.status.toLowerCase()">{{ retakeStatusNames[row.status as keyof typeof retakeStatusNames] }}</span></template></el-table-column><el-table-column label="提交时间" min-width="150"><template #default="{ row }">{{ formatTime(row.createdAt) }}</template></el-table-column><el-table-column label="操作" min-width="140"><template #default="{ row }"><el-button type="primary" link @click="openDetail(row.id)">{{ pendingStage === row.status ? '处理审核' : '详情' }}</el-button><el-button v-if="isStudent && row.status === 'APPROVED'" type="primary" link @click="chooseClass(row.id)">选课</el-button></template></el-table-column></el-table><div class="pagination"><el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="refresh" /></div></section>
    <RetakeClasses v-else-if="tab === 'classes'" :actor="actor" :meta="meta" :applications="approvedApplications" :initial-application-id="selectedApplicationId" @changed="changed" @start-application="startApplication" />
    <section v-else-if="tab === 'timetable'" class="panel" v-loading="timetableBusy"><div class="panel-title"><h3>在修与重修课表</h3><el-select v-model="timetableTerm" aria-label="课表学期" style="width: 300px; max-width: 100%" @change="loadTimetable"><el-option v-for="term in meta.terms" :key="term.id" :value="term.id" :label="term.name" /></el-select></div><el-alert v-if="timetableError" type="error" :title="timetableError" :closable="false" /><el-table :data="timetable" empty-text="该学期暂无上课安排"><el-table-column label="课程类型" width="120"><template #default="{ row }"><el-tag :type="row.source === 'RETAKE' ? 'warning' : 'info'">{{ row.source === 'RETAKE' ? '重修课程' : '在修课程' }}</el-tag></template></el-table-column><el-table-column prop="courseName" label="课程" min-width="150" /><el-table-column prop="className" label="班级" min-width="210" /><el-table-column label="上课时间" min-width="260"><template #default="{ row }">{{ slotLabel(row.slot) }}</template></el-table-column><el-table-column prop="room" label="教室" width="100" /></el-table><p class="m2-table-note">课表显示当前未出分的在修课程及已选重修班级；周次与节次按学校课表口径展示。</p></section>
  </div>
  <el-dialog v-model="formOpen" title="新建重修申请" width="min(620px, 95vw)" :close-on-click-modal="!submitting"><form class="m2-form" @submit.prevent="submit"><el-alert title="演示资格：本人已有不及格成绩的课程；同一课程与学期仅一份有效申请。" type="info" :closable="false" show-icon /><label for="retake-course">不及格课程</label><el-select id="retake-course" v-model="formEnrollmentId" placeholder="暂无符合资格课程时无法提交" aria-label="不及格课程"><el-option v-for="course in meta.eligibleCourses" :key="course.id" :value="course.id" :label="`${course.courseName} · 原成绩 ${course.score} 分`" /></el-select><label for="retake-term">重修学期</label><el-select id="retake-term" v-model="formTermId" aria-label="重修学期"><el-option v-for="term in meta.terms" :key="term.id" :value="term.id" :label="term.name" /></el-select><label for="retake-reason">申请理由</label><el-input id="retake-reason" v-model="reason" type="textarea" :rows="5" maxlength="1000" show-word-limit placeholder="说明本次重修申请原因（10–1000字）" /><p v-if="formError" class="form-error" role="alert">{{ formError }}</p><div class="form-actions"><el-button :disabled="submitting" @click="formOpen = false">取消</el-button><el-button type="primary" native-type="submit" :loading="submitting" :disabled="!meta.eligibleCourses.length">提交重修申请</el-button></div></form></el-dialog>
  <el-drawer v-model="drawerOpen" title="重修申请详情" size="min(680px, 100vw)" destroy-on-close><RetakeDetail v-if="detail" :key="detail.application.id" :actor="actor" :detail="detail" @reviewed="reviewed" @choose-class="chooseClass" /></el-drawer>
</template>
