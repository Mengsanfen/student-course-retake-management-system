let csrf: { token: string; headerName: string } | null = null
export class ApiError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function refreshCsrf() {
  const response = await fetch('/api/v1/auth/csrf', { credentials: 'same-origin' })
  if (!response.ok) throw new ApiError('安全令牌获取失败，请刷新重试', response.status)
  csrf = await response.json()
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers = new Headers(options.headers)
  if (method !== 'GET') {
    if (!csrf) await refreshCsrf()
    headers.set(csrf!.headerName, csrf!.token)
  }
  if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: `服务请求失败 (${response.status})` }))
    throw new ApiError(error.message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
export async function login(username: string, password: string) {
  await refreshCsrf()
  await request('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username, password }).toString() })
  await refreshCsrf()
}
export async function logout() {
  await request('/auth/logout', { method: 'POST' })
  csrf = null
}
