import type { Approval, Course } from './types'

export type RetakeStatus = 'DEPARTMENT_REVIEW' | 'SCHOOL_REVIEW' | 'APPROVED' | 'REJECTED' | 'ENROLLED'
export interface TimeSlot { startWeek: number; endWeek: number; weekday: number; startPeriod: number; endPeriod: number }
export interface Term { id: number; name: string; weekCount: number }
export interface RetakeMeta { terms: Term[]; eligibleCourses: Course[]; courses: { id: number; name: string; code: string }[]; teachers: { id: number; name: string }[] }
export interface RetakeApplication { id: number; studentId: number; enrollmentId: number; courseId: number; courseName: string; courseCode: string; score: number; studentName: string; studentNumber: string; departmentName: string; termId: number; term: string; reason: string; status: RetakeStatus; classId: number | null; className: string | null; createdAt: string; updatedAt: string }
export interface RetakeDetail { application: RetakeApplication; approvals: Approval[] }
export interface RetakeClass { id: number; name: string; courseId: number; courseName: string; courseCode: string; termId: number; term: string; teacherId: number; teacherName: string; capacity: number; enrolledCount: number; room: string; status: 'OPEN' | 'CLOSED'; slots: TimeSlot[] }
export interface ConflictItem { source: 'REGULAR' | 'RETAKE'; courseName: string; className: string; existingSlot: TimeSlot; requestedSlot: TimeSlot; explanation: string }
export interface ConflictResult { allowed: boolean; reasons: string[]; conflicts: ConflictItem[]; alternatives: RetakeClass[] }
export interface RosterEntry { id: number; applicationId: number; studentName: string; studentNumber: string; departmentName: string }
export interface TimetableEntry { source: 'REGULAR' | 'RETAKE'; courseName: string; className: string; room: string; slot: TimeSlot }
export const retakeStatusNames: Record<RetakeStatus, string> = { DEPARTMENT_REVIEW: '待院系审核', SCHOOL_REVIEW: '待校教务审核', APPROVED: '可选重修班', REJECTED: '已驳回', ENROLLED: '已选课' }
export const slotLabel = (slot: TimeSlot) => `第${slot.startWeek}–${slot.endWeek}周 · 周${'一二三四五六日'[slot.weekday - 1]} · ${slot.startPeriod}–${slot.endPeriod}节`
