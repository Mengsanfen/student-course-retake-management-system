<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Actor, Detail, Status } from '../types'
import { formatTime, roleStages, statusNames } from '../types'
import { request } from '../api'
const props = defineProps<{ detail: Detail; actor: Actor }>()
const emit = defineEmits<{ reviewed: [detail: Detail] }>()
const comment = ref('')
const busy = ref(false)
const error = ref('')
const canReview = computed(() => roleStages[props.actor.role] === props.detail.application.status)
const stages: Status[] = ['TEACHER_REVIEW', 'DEPARTMENT_REVIEW', 'SCHOOL_REVIEW']
const stageLabels = ['任课教师审核', '院系教务审核', '校教务终审']
const stageIndex = computed(() => props.detail.application.status === 'APPROVED' ? 3 : props.detail.approvals.length)
async function review(decision: 'APPROVE' | 'REJECT') {
  if (decision === 'REJECT' && !comment.value.trim()) { error.value = '请填写驳回原因，方便学生补充或修正'; return }
  busy.value = true; error.value = ''
  try {
    const result = await request<Detail>(`/deferrals/${props.detail.application.id}/reviews`, { method: 'POST', body: JSON.stringify({ decision, comment: comment.value.trim() }) })
    ElMessage.success(decision === 'APPROVE' ? '已通过本级审核' : '申请已驳回'); emit('reviewed', result)
  } catch (e) { error.value = e instanceof Error ? e.message : '操作失败' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="detail-content"><div class="detail-heading"><span class="eyebrow">缓考申请 #{{ detail.application.id }}</span><h2>{{ detail.application.courseName }}</h2><el-tag :type="detail.application.status === 'REJECTED' ? 'danger' : detail.application.status === 'APPROVED' ? 'success' : 'warning'">{{ statusNames[detail.application.status] }}</el-tag></div>
    <dl class="detail-meta"><div><dt>申请人</dt><dd>{{ detail.application.studentName }} · {{ detail.application.studentNumber }}</dd></div><div><dt>所属院系</dt><dd>{{ detail.application.departmentName }}</dd></div><div><dt>申请时间</dt><dd>{{ formatTime(detail.application.createdAt) }}</dd></div><div><dt>学期</dt><dd>{{ detail.application.term }}</dd></div></dl>
    <h3>申请理由</h3><p class="reason-text">{{ detail.application.reason }}</p><h3>证明材料</h3><a class="attachment-link" :href="`/api/v1/attachments/${detail.application.attachmentId}`" target="_blank" rel="noopener">{{ detail.application.attachmentName }} <span>下载材料</span></a>
    <h3 class="timeline-title">办理轨迹</h3><el-timeline><el-timeline-item :timestamp="formatTime(detail.application.createdAt)" placement="top" type="success"><b>申请已提交</b><p>{{ detail.application.studentName }} 提交了缓考申请</p></el-timeline-item><el-timeline-item v-for="(stage, index) in stages" :key="stage" :timestamp="detail.approvals.find(a => a.stage === stage) ? formatTime(detail.approvals.find(a => a.stage === stage)!.createdAt) : ''" placement="top" :type="detail.approvals.find(a => a.stage === stage)?.decision === 'REJECT' ? 'danger' : index < stageIndex ? 'success' : 'info'"><b>{{ stageLabels[index] }}</b><template v-if="detail.approvals.find(a => a.stage === stage)"><p>{{ detail.approvals.find(a => a.stage === stage)!.reviewerName }} · {{ detail.approvals.find(a => a.stage === stage)!.decision === 'APPROVE' ? '审核通过' : '驳回申请' }}</p><p v-if="detail.approvals.find(a => a.stage === stage)!.comment" class="review-comment">{{ detail.approvals.find(a => a.stage === stage)!.comment }}</p></template><p v-else class="muted">{{ detail.application.status === 'REJECTED' ? '流程已终止' : index === stageIndex ? '等待处理' : '等待上一节点完成' }}</p></el-timeline-item></el-timeline>
    <form v-if="canReview" class="review-form" @submit.prevent="review('APPROVE')"><h3>处理本级审核</h3><label for="review-comment">审核意见（驳回必填）</label><el-input id="review-comment" v-model="comment" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="请核对申请理由和证明材料后填写意见" /><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><el-button type="danger" plain :disabled="busy" @click="review('REJECT')">驳回申请</el-button><el-button type="primary" :loading="busy" native-type="submit">通过本级审核</el-button></div></form>
  </div>
</template>
