export type Role = 'STUDENT' | 'TEACHER' | 'DEPARTMENT_ADMIN' | 'SCHOOL_ADMIN'
export type Status = 'TEACHER_REVIEW' | 'DEPARTMENT_REVIEW' | 'SCHOOL_REVIEW' | 'APPROVED' | 'REJECTED'
export interface Actor { id: number; username: string; displayName: string; role: Role; departmentId: number; departmentName: string }
export interface Course { id: number; courseName: string; courseCode: string; term: string; credits: number; teacherName: string; examAt: string; score: number | null }
export interface Application { id: number; enrollmentId: number; attachmentId: number; attachmentName: string; courseName: string; courseCode: string; studentName: string; studentNumber: string; departmentName: string; term: string; reason: string; status: Status; createdAt: string; updatedAt: string }
export interface Approval { id: number; stage: Status; reviewerName: string; decision: 'APPROVE' | 'REJECT'; comment: string; createdAt: string }
export interface Detail { application: Application; approvals: Approval[] }
export interface Notice { id: number; title: string; content: string; applicationId: number | null; isRead: boolean; createdAt: string }
export interface Page<T> { items: T[]; page: number; size: number; total: number }
export const roleNames: Record<Role, string> = { STUDENT: '学生', TEACHER: '授课教师', DEPARTMENT_ADMIN: '院系教务', SCHOOL_ADMIN: '校教务' }
export const statusNames: Record<Status, string> = { TEACHER_REVIEW: '待教师审核', DEPARTMENT_REVIEW: '待院系审核', SCHOOL_REVIEW: '待校教务审核', APPROVED: '已通过', REJECTED: '已驳回' }
export const roleStages: Partial<Record<Role, Status>> = { TEACHER: 'TEACHER_REVIEW', DEPARTMENT_ADMIN: 'DEPARTMENT_REVIEW', SCHOOL_ADMIN: 'SCHOOL_REVIEW' }
export const formatTime = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
