const API_BASE = import.meta.env.VITE_API_BASE || '/api'

let token = localStorage.getItem('token')

export function setToken(newToken) {
  token = newToken
  if (newToken) {
    localStorage.setItem('token', newToken)
  } else {
    localStorage.removeItem('token')
  }
}

export function getToken() {
  return token
}

function buildHeaders(extraHeaders = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  return headers
}

async function request(endpoint, options = {}) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: buildHeaders(options.headers),
  })

  const contentType = res.headers.get('content-type') || ''

  if (!res.ok) {
    let message = 'Ошибка запроса'

    if (contentType.includes('application/json')) {
      const error = await res.json().catch(() => ({}))
      message = error.detail || error.message || message
    } else {
      const text = await res.text().catch(() => '')
      if (text) message = text
    }

    throw new Error(message)
  }

  if (res.status === 204) {
    return null
  }

  if (contentType.includes('application/json')) {
    return res.json()
  }

  const text = await res.text()
  return text ? JSON.parse(text) : null
}

export async function createUser(name) {
  return request('/users', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function getUserToken(userId) {
  return request(`/users/${userId}/token`)
}

export async function getMe() {
  return request('/users/me')
}

export async function updateUser(name) {
  return request('/users/me', {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export async function deleteUser() {
  return request('/users/me', { method: 'DELETE' })
}

export async function createPost(title, text) {
  return request('/posts', {
    method: 'POST',
    body: JSON.stringify({ title, text }),
  })
}

export async function getMyPosts(limit = 10, offset = 0) {
  return request(`/users/me/posts?limit=${limit}&offset=${offset}`)
}

export async function getPost(id) {
  return request(`/posts/${id}`)
}

export async function updatePost(id, data) {
  return request(`/posts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deletePost(id) {
  return request(`/posts/${id}`, { method: 'DELETE' })
}
