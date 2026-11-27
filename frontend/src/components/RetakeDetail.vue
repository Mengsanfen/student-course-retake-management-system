<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '../api'
import type { Actor } from '../types'
import { formatTime } from '../types'
import type { RetakeDetail } from '../retake-types'
import { retakeStatusNames } from '../retake-types'
const props = defineProps<{ actor: Actor; detail: RetakeDetail }>()
const emit = defineEmits<{ reviewed: [value: RetakeDetail]; chooseClass: [id: number] }>()
const comment = ref('')
const busy = ref(false)
const error = ref('')
const canReview = computed(() => (props.actor.role === 'DEPARTMENT_ADMIN' && props.detail.application.status === 'DEPARTMENT_REVIEW') || (props.actor.role === 'SCHOOL_ADMIN' && props.detail.application.status === 'SCHOOL_REVIEW'))
async function review(decision: 'APPROVE' | 'REJECT') {
  error.value = ''
  if (decision === 'REJECT' && !comment.value.trim()) { error.value = '请填写驳回原因'; return }
  busy.value = true
  try {
    const result = await request<RetakeDetail>(`/retakes/${props.detail.application.id}/reviews`, { method: 'POST', body: JSON.stringify({ decision, comment: comment.value.trim() }) })
    emit('reviewed', result); ElMessage.success('审核结果已保存')
  } catch (e) { error.value = e instanceof Error ? e.message : '审核失败' }
  finally { busy.value = false }
}
</script>
<template>
  <div class="detail-content"><div class="detail-heading"><span class="eyebrow">重修申请 #{{ detail.application.id }}</span><h2>{{ detail.application.courseName }}</h2><el-tag :type="detail.application.status === 'REJECTED' ? 'danger' : ['APPROVED', 'ENROLLED'].includes(detail.application.status) ? 'success' : 'warning'">{{ retakeStatusNames[detail.application.status] }}</el-tag></div>
    <dl class="detail-meta"><div><dt>申请人</dt><dd>{{ detail.application.studentName }} · {{ detail.application.studentNumber }}</dd></div><div><dt>所属院系</dt><dd>{{ detail.application.departmentName }}</dd></div><div><dt>原课程成绩</dt><dd>{{ detail.application.score }} 分</dd></div><div><dt>重修学期</dt><dd>{{ detail.application.term }}</dd></div><div><dt>提交时间</dt><dd>{{ formatTime(detail.application.createdAt) }}</dd></div><div v-if="detail.application.className"><dt>已选重修班</dt><dd>{{ detail.application.className }}</dd></div></dl>
    <h3>申请理由</h3><p class="reason-text">{{ detail.application.reason }}</p><h3 class="timeline-title">办理轨迹</h3><el-timeline><el-timeline-item type="success" :timestamp="formatTime(detail.application.createdAt)" placement="top"><b>申请已提交</b></el-timeline-item><el-timeline-item v-for="stage in ['DEPARTMENT_REVIEW', 'SCHOOL_REVIEW']" :key="stage" :type="detail.approvals.find(row => row.stage === stage)?.decision === 'REJECT' ? 'danger' : detail.approvals.some(row => row.stage === stage) ? 'success' : 'info'" :timestamp="detail.approvals.find(row => row.stage === stage) ? formatTime(detail.approvals.find(row => row.stage === stage)!.createdAt) : ''" placement="top"><b>{{ stage === 'DEPARTMENT_REVIEW' ? '院系审核' : '校教务终审' }}</b><template v-if="detail.approvals.find(row => row.stage === stage)"><p>{{ detail.approvals.find(row => row.stage === stage)!.reviewerName }} · {{ detail.approvals.find(row => row.stage === stage)!.decision === 'APPROVE' ? '审核通过' : '已驳回' }}</p><p class="review-comment">{{ detail.approvals.find(row => row.stage === stage)!.comment || '无补充意见' }}</p></template><p v-else class="muted">{{ detail.application.status === 'REJECTED' ? '流程已终止' : '等待处理' }}</p></el-timeline-item><el-timeline-item v-if="detail.application.className" type="success"><b>重修选课成功</b><p>{{ detail.application.className }}</p></el-timeline-item></el-timeline>
    <el-button v-if="actor.role === 'STUDENT' && detail.application.status === 'APPROVED'" type="primary" @click="emit('chooseClass', detail.application.id)">选择重修班级</el-button>
    <form v-if="canReview" class="review-form" @submit.prevent="review('APPROVE')"><h3>处理当前节点</h3><label for="retake-review-comment">审核意见（驳回必填）</label><el-input id="retake-review-comment" v-model="comment" type="textarea" :rows="3" maxlength="500" show-word-limit /><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><el-button type="danger" plain :disabled="busy" @click="review('REJECT')">驳回申请</el-button><el-button type="primary" native-type="submit" :loading="busy">通过本级审核</el-button></div></form>
  </div>
</template>
