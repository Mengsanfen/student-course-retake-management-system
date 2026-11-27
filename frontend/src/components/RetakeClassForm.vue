<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '../api'
import type { RetakeClass, RetakeMeta, TimeSlot } from '../retake-types'
const props = defineProps<{ meta: RetakeMeta }>()
const emit = defineEmits<{ created: [value: RetakeClass] }>()
const form = reactive({ name: '', courseId: props.meta.courses[0]?.id, termId: props.meta.terms[0]?.id, teacherId: props.meta.teachers[0]?.id, capacity: 20, room: '' })
const slots = ref<TimeSlot[]>([{ startWeek: 1, endWeek: 16, weekday: 2, startPeriod: 7, endPeriod: 8 }])
const busy = ref(false)
const error = ref('')
async function submit() {
  error.value = ''
  if (!form.courseId || !form.termId || !form.teacherId || form.name.trim().length < 2 || !form.room.trim()) { error.value = '请完整填写班级名称、课程、学期、教师及教室'; return }
  if (slots.value.some(slot => slot.startWeek > slot.endWeek || slot.startPeriod > slot.endPeriod)) { error.value = '结束周次和节次不得早于开始'; return }
  busy.value = true
  try {
    const value = await request<RetakeClass>('/retake-classes', { method: 'POST', body: JSON.stringify({ ...form, name: form.name.trim(), room: form.room.trim(), slots: slots.value }) })
    ElMessage.success('重修班级已开设'); emit('created', value)
  } catch (e) { error.value = e instanceof Error ? e.message : '开班失败' }
  finally { busy.value = false }
}
</script>
<template>
  <form class="m2-form" @submit.prevent="submit">
    <label for="class-name">班级名称</label><el-input id="class-name" v-model="form.name" maxlength="80" placeholder="例如：程序设计基础 · 周末班" />
    <div class="m2-form-grid"><div><label for="class-course">重修课程</label><el-select id="class-course" v-model="form.courseId" aria-label="重修课程"><el-option v-for="course in meta.courses" :key="course.id" :value="course.id" :label="`${course.name} · ${course.code}`" /></el-select></div><div><label for="class-term">开班学期</label><el-select id="class-term" v-model="form.termId" aria-label="开班学期"><el-option v-for="term in meta.terms" :key="term.id" :value="term.id" :label="term.name" /></el-select></div><div><label for="class-teacher">授课教师</label><el-select id="class-teacher" v-model="form.teacherId" aria-label="授课教师"><el-option v-for="teacher in meta.teachers" :key="teacher.id" :value="teacher.id" :label="teacher.name" /></el-select></div><div><label for="class-room">上课教室</label><el-input id="class-room" v-model="form.room" maxlength="60" placeholder="例如 C301" /></div><div><label for="class-capacity">班级容量</label><el-input-number id="class-capacity" v-model="form.capacity" :min="1" :max="200" /></div></div>
    <div class="m2-section-heading"><h3>上课时间</h3><el-button :disabled="slots.length >= 8" @click="slots.push({ startWeek: 1, endWeek: 16, weekday: 2, startPeriod: 1, endPeriod: 2 })">添加时间段</el-button></div>
    <div v-for="(slot, index) in slots" :key="index" class="m2-slot-editor"><div><label :for="`slot-day-${index}`">星期</label><el-select :id="`slot-day-${index}`" v-model="slot.weekday" aria-label="上课星期"><el-option v-for="day in 7" :key="day" :value="day" :label="`周${'一二三四五六日'[day - 1]}`" /></el-select></div><div><label :for="`slot-start-week-${index}`">开始周</label><el-input-number :id="`slot-start-week-${index}`" v-model="slot.startWeek" :min="1" :max="30" controls-position="right" /></div><div><label :for="`slot-end-week-${index}`">结束周</label><el-input-number :id="`slot-end-week-${index}`" v-model="slot.endWeek" :min="1" :max="30" controls-position="right" /></div><div><label :for="`slot-start-period-${index}`">开始节</label><el-input-number :id="`slot-start-period-${index}`" v-model="slot.startPeriod" :min="1" :max="12" controls-position="right" /></div><div><label :for="`slot-end-period-${index}`">结束节</label><el-input-number :id="`slot-end-period-${index}`" v-model="slot.endPeriod" :min="1" :max="12" controls-position="right" /></div><el-button type="danger" text :disabled="slots.length === 1" :aria-label="`删除第${index + 1}个时间段`" @click="slots.splice(index, 1)">删除</el-button></div>
    <p class="muted">开班时会检查教师、教室占用以及班内时间段是否重叠。周次按所选学期计算。</p><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><el-button type="primary" native-type="submit" :loading="busy">确认开班</el-button></div>
  </form>
</template>
