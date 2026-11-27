<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '../api'
import type { Actor, Page } from '../types'
import type { ConflictResult, RetakeApplication, RetakeClass, RetakeMeta, RosterEntry } from '../retake-types'
import { slotLabel } from '../retake-types'
import RetakeClassForm from './RetakeClassForm.vue'
const props = defineProps<{ actor: Actor; meta: RetakeMeta; applications: RetakeApplication[]; initialApplicationId: number | null }>()
const emit = defineEmits<{ changed: []; startApplication: [] }>()
const rows = ref<RetakeClass[]>([])
const total = ref(0)
const page = ref(1)
const selectedId = ref<number | undefined>(props.initialApplicationId ?? undefined)
const busy = ref(false)
const error = ref('')
const showCreate = ref(false)
const showCheck = ref(false)
const checking = ref(false)
const selectedClass = ref<RetakeClass | null>(null)
const result = ref<ConflictResult | null>(null)
const checkError = ref('')
const showRoster = ref(false)
const roster = ref<RosterEntry[]>([])
const rosterName = ref('')
const editing = ref<RetakeClass | null>(null)
const editCapacity = ref(20)
const editStatus = ref<'OPEN' | 'CLOSED'>('OPEN')
const editError = ref('')
const editBusy = ref(false)
async function load() {
  busy.value = true; error.value = ''
  const selected = props.applications.find(a => a.id === selectedId.value)
  const filter = selected ? `&termId=${selected.termId}&courseId=${selected.courseId}` : ''
  try { const data = await request<Page<RetakeClass>>(`/retake-classes?page=${page.value}&size=12${filter}`); rows.value = data.items; total.value = data.total }
  catch (e) { error.value = e instanceof Error ? e.message : '班级加载失败' }
  finally { busy.value = false }
}
watch(selectedId, () => { page.value = 1; void load() })
watch(() => props.initialApplicationId, value => { selectedId.value = value ?? undefined })
watch(() => props.applications, list => { if (selectedId.value && !list.some(a => a.id === selectedId.value)) selectedId.value = undefined })
onMounted(load)
async function inspect(target: RetakeClass) {
  if (!selectedId.value) { ElMessage.info('请先选择一份已通过的重修申请'); return }
  selectedClass.value = target; showCheck.value = true; checking.value = true; result.value = null; checkError.value = ''
  try { result.value = await request<ConflictResult>(`/retake-classes/${target.id}/conflict-check`, { method: 'POST', body: JSON.stringify({ applicationId: selectedId.value }) }) }
  catch (e) { checkError.value = e instanceof Error ? e.message : '检查失败' }
  finally { checking.value = false }
}
async function enroll() {
  if (!selectedId.value || !selectedClass.value || !result.value?.allowed) return
  checking.value = true; checkError.value = ''
  try {
    await request('/retake-enrollments', { method: 'POST', body: JSON.stringify({ applicationId: selectedId.value, classId: selectedClass.value.id }) })
    ElMessage.success('选课成功，请在我的课表查看安排'); showCheck.value = false; emit('changed'); await load()
  } catch (e) { checkError.value = e instanceof Error ? e.message : '选课失败，请刷新后检查' }
  finally { checking.value = false }
}
async function openRoster(target: RetakeClass) {
  try { roster.value = await request<RosterEntry[]>(`/retake-classes/${target.id}/students`); rosterName.value = target.name; showRoster.value = true }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '名单加载失败') }
}
function edit(target: RetakeClass) { editing.value = target; editCapacity.value = target.capacity; editStatus.value = target.status; editError.value = '' }
async function saveEdit() {
  if (!editing.value) return
  editBusy.value = true
  try { await request(`/retake-classes/${editing.value.id}`, { method: 'PATCH', body: JSON.stringify({ capacity: editCapacity.value, status: editStatus.value }) }); editing.value = null; ElMessage.success('班级设置已保存'); await load() }
  catch (e) { editError.value = e instanceof Error ? e.message : '保存失败' }
  finally { editBusy.value = false }
}
async function created() { showCreate.value = false; page.value = 1; await load(); emit('changed') }
</script>
<template>
  <section class="m2-catalog" v-loading="busy"><div class="m2-toolbar"><div v-if="actor.role === 'STUDENT'" class="m2-selection"><label for="retake-approved">用于选课的已通过申请</label><el-select id="retake-approved" v-model="selectedId" placeholder="先完成重修申请与审核" clearable aria-label="用于选课的已通过申请"><el-option v-for="application in applications" :key="application.id" :value="application.id" :label="`${application.courseName} · #${application.id} · ${application.term}`" /></el-select><el-button v-if="!applications.length" @click="emit('startApplication')">申请重修</el-button></div><p v-else class="muted">{{ actor.role === 'TEACHER' ? '以下是你负责的重修班级，可查看已选课学生。' : '开班信息与实际选课人数同步，暂停选课会保留名册。' }}</p><div class="m2-toolbar-actions"><el-button @click="load">刷新班级</el-button><el-button v-if="actor.role === 'SCHOOL_ADMIN'" type="primary" @click="showCreate = true">开设重修班</el-button></div></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <div class="m2-class-grid"><article v-for="target in rows" :key="target.id" class="panel m2-class-card"><div class="m2-class-card-top"><span>{{ target.courseCode }}</span><el-tag :type="target.status === 'CLOSED' ? 'info' : target.enrolledCount >= target.capacity ? 'warning' : 'success'">{{ target.status === 'CLOSED' ? '暂停选课' : target.enrolledCount >= target.capacity ? '已满员' : '可选课' }}</el-tag></div><h3>{{ target.name }}</h3><p class="m2-class-term">{{ target.term }}</p><div class="m2-class-info"><span>授课教师 <b>{{ target.teacherName }}</b></span><span>教室 <b>{{ target.room }}</b></span></div><div class="m2-time-list"><p v-for="(slot, index) in target.slots" :key="index">{{ slotLabel(slot) }}</p></div><div class="m2-capacity"><span>已选 {{ target.enrolledCount }} / {{ target.capacity }} 人</span><div><i :style="{ width: `${Math.min(100, target.enrolledCount / target.capacity * 100)}%` }"></i></div></div><div class="m2-class-actions"><el-button v-if="actor.role === 'STUDENT'" type="primary" plain :disabled="!selectedId" @click="inspect(target)">检查时间与名额</el-button><el-button v-else @click="openRoster(target)">查看学生名单</el-button><el-button v-if="actor.role === 'SCHOOL_ADMIN'" text @click="edit(target)">调整班级</el-button></div></article></div><el-empty v-if="!rows.length && !busy" description="暂无符合条件的重修班级" /><div class="pagination"><el-pagination v-model:current-page="page" :total="total" :page-size="12" layout="total, prev, pager, next" @current-change="load" /></div>
  </section>
  <el-dialog v-model="showCreate" title="开设重修班级" width="min(900px, 95vw)" destroy-on-close><RetakeClassForm v-if="showCreate" :meta="meta" @created="created" /></el-dialog>
  <el-dialog v-model="showCheck" :title="selectedClass?.name ?? '选课检查'" width="min(720px, 95vw)"><div v-loading="checking" class="m2-conflict-result"><el-alert v-if="result" :title="result.allowed ? '时间与名额检查通过，可以确认选课' : result.reasons.join('；')" :type="result.allowed ? 'success' : 'warning'" :closable="false" show-icon /><p v-if="selectedClass" class="muted m2-check-summary">{{ selectedClass.teacherName }} · {{ selectedClass.room }}<br><span v-for="(slot, index) in selectedClass.slots" :key="index">{{ slotLabel(slot) }}<br></span></p><div v-for="(item, index) in result?.conflicts ?? []" :key="index" class="m2-conflict-item"><b>{{ item.source === 'REGULAR' ? '在修课程' : '已选重修课' }} · {{ item.courseName }}</b><p>{{ item.explanation }}</p></div><div v-if="result?.alternatives.length" class="m2-alternatives"><h3>可选的其他班级</h3><button v-for="alternative in result.alternatives" :key="alternative.id" @click="inspect(alternative)"><b>{{ alternative.name }}</b><span>{{ alternative.teacherName }} · 余 {{ alternative.capacity - alternative.enrolledCount }} 位</span><span>{{ alternative.slots.map(slotLabel).join(' / ') }}</span></button></div><p v-if="checkError" class="form-error" role="alert">{{ checkError }}</p><p class="muted">确认时会再次检查，实际名额以提交结果为准。</p></div><template #footer><el-button @click="showCheck = false">关闭</el-button><el-button v-if="result?.allowed" type="primary" :loading="checking" @click="enroll">确认选课</el-button></template></el-dialog>
  <el-dialog v-model="showRoster" :title="`${rosterName} · 学生名单`" width="min(760px, 95vw)"><el-table :data="roster" empty-text="暂无学生；院系教务仅查看本院学生"><el-table-column prop="studentNumber" label="学号" min-width="120" /><el-table-column prop="studentName" label="学生姓名" min-width="110" /><el-table-column prop="departmentName" label="院系" min-width="210" /></el-table></el-dialog>
  <el-dialog :model-value="!!editing" title="调整班级" width="min(480px, 95vw)" @close="editing = null"><label for="edit-class-status">选课状态</label><el-select id="edit-class-status" v-model="editStatus" aria-label="选课状态"><el-option value="OPEN" label="开放选课" /><el-option value="CLOSED" label="暂停选课" /></el-select><label for="edit-class-capacity">容量（已选 {{ editing?.enrolledCount ?? 0 }} 人）</label><el-input-number id="edit-class-capacity" v-model="editCapacity" :min="Math.max(1, editing?.enrolledCount ?? 0)" :max="200" /><p v-if="editError" class="form-error" role="alert">{{ editError }}</p><template #footer><el-button @click="editing = null">取消</el-button><el-button type="primary" :loading="editBusy" @click="saveEdit">保存设置</el-button></template></el-dialog>
</template>
