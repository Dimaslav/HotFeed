const API_BASE = '/api';

let token = localStorage.getItem('token');

export function setToken(newToken) {
  token = newToken;
  if (newToken) {
    localStorage.setItem('token', newToken);
  } else {
    localStorage.removeItem('token');
  }
}

export function getToken() {
  return token;
}

async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Ошибка запроса');
  }
  return res.json();
}

export async function createUser(name) {
  return request('/users', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function getUserToken(userId) {
  return request(`/users/${userId}/token`);
}

export async function getMe() {
  return request('/users/me');
}

export async function updateUser(name) {
  return request('/users/me', {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export async function deleteUser() {
  return request('/users/me', { method: 'DELETE' });
}

export async function createPost(title, text) {
  return request('/posts', {
    method: 'POST',
    body: JSON.stringify({ title, text }),
  });
}

export async function getMyPosts(limit = 10, offset = 0) {
  return request(`/users/me/posts?limit=${limit}&offset=${offset}`);
}

export async function getPost(id) {
  return request(`/posts/${id}`);
}

export async function updatePost(id, data) {
  return request(`/posts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deletePost(id) {
  return request(`/posts/${id}`, { method: 'DELETE' });
}