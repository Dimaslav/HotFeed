<template>
  <div class="container">
    <header class="header">
      <div>
        <h1>Лента публикаций</h1>
        <p class="subtitle">
          Создавайте посты, редактируйте профиль и открывайте публикации по ID.
        </p>
      </div>

      <div v-if="user" class="user-info">
        <span>#{{ user.id }} · {{ user.name }}</span>
        <button type="button" class="secondary" :disabled="busy" @click="refreshAll">
          Обновить
        </button>
        <button type="button" class="secondary" :disabled="busy" @click="handleLogout">
          Выйти
        </button>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <div v-if="busy && !user" class="loader">Загрузка...</div>

    <section v-else-if="!user" class="auth-grid">
      <form class="card auth-modal" @submit.prevent="handleCreateAccount">
        <h2>Создать пользователя</h2>

        <label>
          Имя
          <input
            v-model.trim="createName"
            type="text"
            placeholder="Ваше имя"
            maxlength="255"
            required
          />
        </label>

        <button type="submit" :disabled="busy || !createName">
          Создать и войти
        </button>
      </form>

      <form class="card auth-modal" @submit.prevent="handleLoginById">
        <h2>Войти по ID</h2>

        <label>
          ID пользователя
          <input
            v-model="loginUserId"
            type="number"
            min="1"
            placeholder="1"
            required
          />
        </label>

        <button type="submit" :disabled="busy || !loginUserId">
          Получить токен
        </button>
      </form>
    </section>

    <section v-else class="dashboard">
      <div v-if="busy" class="loader">Выполняется операция...</div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Профиль</h2>
            <p class="meta">
              Создан: {{ formatDate(user.created_at) }} ·
              Обновлён: {{ formatDate(user.updated_at) }}
            </p>
          </div>
        </div>

        <form class="inline-form" @submit.prevent="handleUpdateProfile">
          <input
            v-model.trim="profileName"
            type="text"
            maxlength="255"
            placeholder="Ваше имя"
            required
          />
          <button type="submit" :disabled="busy || !profileName">
            Сохранить
          </button>
          <button
            type="button"
            class="secondary"
            :disabled="busy"
            @click="profileName = user.name"
          >
            Сбросить
          </button>
        </form>

        <div class="actions">
          <button type="button" class="danger" :disabled="busy" @click="handleDeleteAccount">
            Удалить аккаунт
          </button>
        </div>
      </div>

      <div class="panel">
        <h2>Новый пост</h2>

        <form class="post-form" @submit.prevent="handleCreatePost">
          <input
            v-model.trim="newPostTitle"
            type="text"
            maxlength="255"
            placeholder="Заголовок"
            required
          />

          <textarea
            v-model.trim="newPostText"
            rows="6"
            placeholder="Текст поста"
            required
          ></textarea>

          <div class="form-footer">
            <button type="submit" :disabled="busy || !newPostTitle || !newPostText">
              Опубликовать
            </button>
          </div>
        </form>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Мои посты</h2>
            <p class="meta">Посты загружаются с пагинацией. Можно открыть пост по ID.</p>
          </div>

          <div class="search-inline">
            <input
              v-model="publicPostId"
              type="number"
              min="1"
              placeholder="ID поста"
            />
            <button
              type="button"
              class="secondary"
              :disabled="busy || !publicPostId"
              @click="handleOpenPostById"
            >
              Открыть
            </button>
          </div>
        </div>

        <div v-if="posts.length" class="post-list">
          <article
            v-for="post in posts"
            :key="post.id"
            class="post-card"
            @click="openPost(post)"
          >
            <h3>{{ post.title }}</h3>
            <p>{{ post.text }}</p>
            <small>#{{ post.id }} · {{ formatDate(post.created_at) }}</small>
          </article>
        </div>

        <div v-else class="empty-state">Пока нет опубликованных постов.</div>

        <div v-if="hasMore" class="list-actions">
          <button type="button" class="secondary" :disabled="busy" @click="loadMore">
            Загрузить ещё
          </button>
        </div>

        <div v-else-if="posts.length" class="end-message">
          Это все ваши посты.
        </div>
      </div>
    </section>

    <transition name="fade">
      <div v-if="selectedPost" class="modal-overlay" @click.self="closePost">
        <div class="modal">
          <button type="button" class="modal-close" @click="closePost">×</button>

          <template v-if="editingPost">
            <h2>Редактировать пост</h2>

            <form @submit.prevent="handleSavePost">
              <label>
                Заголовок
                <input
                  v-model.trim="editTitle"
                  type="text"
                  maxlength="255"
                  required
                />
              </label>

              <label>
                Текст
                <textarea v-model.trim="editText" rows="10" required></textarea>
              </label>

              <div class="modal-actions">
                <button type="submit" :disabled="busy || !editTitle || !editText">
                  Сохранить
                </button>
                <button type="button" class="secondary" :disabled="busy" @click="cancelEdit">
                  Отмена
                </button>
              </div>
            </form>
          </template>

          <template v-else>
            <h2>{{ selectedPost.title }}</h2>
            <p>{{ selectedPost.text }}</p>

            <div class="meta">
              <div>ID: {{ selectedPost.id }} · Автор: #{{ selectedPost.user_id }}</div>
              <div>Создан: {{ formatDate(selectedPost.created_at) }}</div>
              <div>Обновлён: {{ formatDate(selectedPost.updated_at) }}</div>
            </div>

            <p v-if="selectedPost.user_id !== user.id" class="meta">
              Этот пост открыт только для просмотра.
            </p>

            <div v-else class="modal-actions">
              <button type="button" :disabled="busy" @click="startEdit">
                Редактировать
              </button>
              <button type="button" class="secondary" :disabled="busy" @click="handleDeleteSelectedPost">
                Удалить
              </button>
            </div>
          </template>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import {
  getToken,
  setToken,
  createUser,
  getUserToken,
  getMe,
  updateUser,
  deleteUser,
  createPost,
  getMyPosts,
  getPost,
  updatePost,
  deletePost,
} from './api'

const PAGE_SIZE = 10

const user = ref(null)
const posts = ref([])
const selectedPost = ref(null)
const editingPost = ref(false)

const createName = ref('')
const loginUserId = ref('')
const profileName = ref('')
const newPostTitle = ref('')
const newPostText = ref('')
const publicPostId = ref('')

const editTitle = ref('')
const editText = ref('')

const busy = ref(false)
const error = ref('')
const notice = ref('')
const hasMore = ref(true)
const postOffset = ref(0)

function clearMessages() {
  error.value = ''
  notice.value = ''
}

function resetFeed() {
  posts.value = []
  postOffset.value = 0
  hasMore.value = true
}

function clearSession() {
  setToken(null)
  user.value = null
  selectedPost.value = null
  editingPost.value = false

  createName.value = ''
  loginUserId.value = ''
  profileName.value = ''
  newPostTitle.value = ''
  newPostText.value = ''
  publicPostId.value = ''
  editTitle.value = ''
  editText.value = ''

  resetFeed()
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function syncSelectedPost() {
  if (!selectedPost.value) return
  const fresh = posts.value.find((post) => post.id === selectedPost.value.id)
  if (fresh) {
    selectedPost.value = fresh
  }
}

async function loadPosts(reset = false) {
  if (!user.value) return

  if (reset) {
    resetFeed()
  }

  if (!hasMore.value) return

  const items = await getMyPosts(PAGE_SIZE, postOffset.value)

  posts.value = reset ? items : [...posts.value, ...items]
  postOffset.value += items.length
  hasMore.value = items.length === PAGE_SIZE

  syncSelectedPost()
}

async function loadSession(token) {
  setToken(token)

  selectedPost.value = null
  editingPost.value = false
  editTitle.value = ''
  editText.value = ''
  newPostTitle.value = ''
  newPostText.value = ''
  publicPostId.value = ''

  const me = await getMe()
  user.value = me
  profileName.value = me.name

  await loadPosts(true)
}

async function handleBootstrap() {
  const savedToken = getToken()
  if (!savedToken) return

  busy.value = true
  clearMessages()

  try {
    await loadSession(savedToken)
  } catch (e) {
    clearSession()
    error.value = e?.message || 'Не удалось восстановить сессию'
  } finally {
    busy.value = false
  }
}

onMounted(handleBootstrap)

async function handleCreateAccount() {
  const name = createName.value.trim()
  if (!name) return

  busy.value = true
  clearMessages()

  try {
    const { access_token } = await createUser(name)
    clearSession()
    await loadSession(access_token)
    notice.value = `Пользователь "${name}" создан и выполнен вход.`
    createName.value = ''
  } catch (e) {
    clearSession()
    error.value = e?.message || 'Не удалось создать пользователя'
  } finally {
    busy.value = false
  }
}

async function handleLoginById() {
  const id = Number(loginUserId.value)
  if (!Number.isFinite(id) || id <= 0) {
    error.value = 'Введите корректный ID пользователя'
    return
  }

  busy.value = true
  clearMessages()

  try {
    const { access_token } = await getUserToken(id)
    clearSession()
    await loadSession(access_token)
    notice.value = `Выполнен вход как пользователь #${id}.`
    loginUserId.value = ''
  } catch (e) {
    clearSession()
    error.value = e?.message || 'Не удалось войти'
  } finally {
    busy.value = false
  }
}

async function refreshAll() {
  if (!user.value) return

  busy.value = true
  clearMessages()

  try {
    const me = await getMe()
    user.value = me
    profileName.value = me.name

    await loadPosts(true)
    syncSelectedPost()

    notice.value = 'Данные обновлены.'
  } catch (e) {
    error.value = e?.message || 'Не удалось обновить данные'
    if (e?.message && /not authenticated|invalid token|user not found/i.test(e.message)) {
      clearSession()
    }
  } finally {
    busy.value = false
  }
}

async function handleUpdateProfile() {
  const name = profileName.value.trim()
  if (!name) return

  busy.value = true
  clearMessages()

  try {
    const updated = await updateUser(name)
    user.value = updated
    profileName.value = updated.name
    notice.value = 'Профиль обновлён.'
  } catch (e) {
    error.value = e?.message || 'Не удалось обновить профиль'
  } finally {
    busy.value = false
  }
}

async function handleDeleteAccount() {
  if (!window.confirm('Удалить аккаунт и все ваши посты?')) return

  busy.value = true
  clearMessages()

  try {
    await deleteUser()
    clearSession()
    notice.value = 'Аккаунт удалён.'
  } catch (e) {
    error.value = e?.message || 'Не удалось удалить аккаунт'
  } finally {
    busy.value = false
  }
}

async function handleCreatePost() {
  const title = newPostTitle.value.trim()
  const text = newPostText.value.trim()
  if (!title || !text) return

  busy.value = true
  clearMessages()

  try {
    await createPost(title, text)
    newPostTitle.value = ''
    newPostText.value = ''

    await loadPosts(true)
    notice.value = 'Пост опубликован.'
  } catch (e) {
    error.value = e?.message || 'Не удалось создать пост'
  } finally {
    busy.value = false
  }
}

async function loadMore() {
  if (!user.value || busy.value || !hasMore.value) return

  busy.value = true
  clearMessages()

  try {
    await loadPosts(false)
  } catch (e) {
    error.value = e?.message || 'Не удалось загрузить посты'
  } finally {
    busy.value = false
  }
}

function openPost(post) {
  if (busy.value) return
  selectedPost.value = { ...post }
  editingPost.value = false
  editTitle.value = ''
  editText.value = ''
}

async function handleOpenPostById() {
  const id = Number(publicPostId.value)
  if (!Number.isFinite(id) || id <= 0) {
    error.value = 'Введите корректный ID поста'
    return
  }

  busy.value = true
  clearMessages()

  try {
    const post = await getPost(id)
    selectedPost.value = { ...post }
    editingPost.value = false
    editTitle.value = ''
    editText.value = ''
  } catch (e) {
    error.value = e?.message || 'Не удалось открыть пост'
  } finally {
    busy.value = false
  }
}

function closePost() {
  selectedPost.value = null
  editingPost.value = false
  editTitle.value = ''
  editText.value = ''
}

function startEdit() {
  if (!selectedPost.value || selectedPost.value.user_id !== user.value.id) return

  editTitle.value = selectedPost.value.title
  editText.value = selectedPost.value.text
  editingPost.value = true
}

function cancelEdit() {
  editingPost.value = false
  editTitle.value = ''
  editText.value = ''
}

async function handleSavePost() {
  if (!selectedPost.value) return

  const title = editTitle.value.trim()
  const text = editText.value.trim()
  if (!title || !text) return

  busy.value = true
  clearMessages()

  try {
    const updated = await updatePost(selectedPost.value.id, { title, text })
    selectedPost.value = { ...updated }
    editingPost.value = false
    editTitle.value = ''
    editText.value = ''

    await loadPosts(true)
    notice.value = 'Пост обновлён.'
  } catch (e) {
    error.value = e?.message || 'Не удалось обновить пост'
  } finally {
    busy.value = false
  }
}

async function handleDeleteSelectedPost() {
  if (!selectedPost.value) return
  if (!window.confirm(`Удалить пост #${selectedPost.value.id}?`)) return

  busy.value = true
  clearMessages()

  try {
    await deletePost(selectedPost.value.id)
    selectedPost.value = null
    editingPost.value = false
    editTitle.value = ''
    editText.value = ''

    await loadPosts(true)
    notice.value = 'Пост удалён.'
  } catch (e) {
    error.value = e?.message || 'Не удалось удалить пост'
  } finally {
    busy.value = false
  }
}

function handleLogout() {
  clearSession()
  clearMessages()
  notice.value = 'Вы вышли из аккаунта.'
}
</script>
