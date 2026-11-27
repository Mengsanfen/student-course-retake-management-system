<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, DocumentChecked } from '@element-plus/icons-vue'
import type { Course, Detail } from '../types'
import { request } from '../api'

const props = defineProps<{ courses: Course[] }>()
const emit = defineEmits<{ submitted: [detail: Detail]; cancel: [] }>()
const enrollmentId = ref<number>()
const reason = ref('')
const file = ref<File | null>(null)
const busy = ref(false)
const error = ref('')
const selected = computed(() => props.courses.find(c => c.id === enrollmentId.value))
function fileChanged(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}
async function submit() {
  error.value = ''
  if (!enrollmentId.value) { error.value = '请选择申请缓考的课程'; return }
  if (reason.value.trim().length < 10) { error.value = '请填写至少10字的申请理由'; return }
  if (!file.value) { error.value = '请上传证明材料'; return }
  if (file.value.size > 5 * 1024 * 1024 || !/\.(pdf|png|jpe?g)$/i.test(file.value.name)) { error.value = '材料须为PDF、PNG或JPEG，且不超过5 MiB'; return }
  busy.value = true
  try {
    const form = new FormData(); form.append('file', file.value)
    const attachment = await request<{ id: number }>('/attachments', { method: 'POST', body: form })
    const detail = await request<Detail>('/deferrals', { method: 'POST', body: JSON.stringify({ enrollmentId: enrollmentId.value, attachmentId: attachment.id, reason: reason.value.trim() }) })
    ElMessage.success('申请已提交，请关注审核进度'); emit('submitted', detail)
  } catch (e) { error.value = e instanceof Error ? e.message : '提交失败，请稍后重试' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="form-layout"><section class="panel application-form"><div class="panel-title"><h3>填写缓考申请</h3><span>带 * 为必填项</span></div>
    <form @submit.prevent="submit"><label for="course">申请课程 <em>*</em></label><el-select id="course" v-model="enrollmentId" placeholder="选择需要申请缓考的课程" size="large" aria-label="申请课程"><el-option v-for="course in courses" :key="course.id" :label="`${course.courseName} · ${course.courseCode}${course.score !== null ? '（已出分）' : ''}`" :value="course.id" :disabled="course.score !== null" /></el-select>
      <p v-if="selected" class="field-hint">{{ selected.term }} · 任课教师 {{ selected.teacherName }}</p>
      <label for="reason">申请理由 <em>*</em></label><el-input id="reason" v-model="reason" type="textarea" :rows="5" :minlength="10" :maxlength="1000" show-word-limit placeholder="请如实说明申请缓考的原因（10–1000字）" />
      <label for="material">证明材料 <em>*</em></label><div class="upload-zone"><el-icon><UploadFilled /></el-icon><b>{{ file?.name ?? '选择证明材料' }}</b><span>支持 PDF / PNG / JPEG，单个文件不超过 5 MiB</span><input id="material" type="file" accept=".pdf,.png,.jpg,.jpeg" aria-label="选择证明材料" @change="fileChanged" :disabled="busy" /></div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><el-button @click="emit('cancel')" :disabled="busy">取消</el-button><el-button type="primary" native-type="submit" :loading="busy">提交申请</el-button></div>
    </form></section>
    <aside class="panel form-help"><el-icon class="help-icon"><DocumentChecked /></el-icon><h3>提交前，请确认</h3><ol><li>申请课程属于本人，尚未出分且未开考。</li><li>申请理由真实、完整，与证明材料一致。</li><li>同一课程仅保留一份有效申请。</li></ol><div class="help-note">提交后依次由任课教师、院系教务和校教务审核。你可以在「我的申请」查看每一步的处理结果。</div><p class="muted">演示规则：考试开始前可申请。学校正式办理期限以教务通知为准。</p></aside>
  </div>
</template>
