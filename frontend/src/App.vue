<template>
  <div class="container">
    <header class="header">
      <h1>Лента публикаций</h1>
      <div class="user-info" v-if="user">
        <span>{{ user.name }}</span>
        <button @click="logout" class="secondary">Выйти</button>
      </div>
      <div v-else>
        <button @click="showAuth = true">Войти / Зарегистрироваться</button>
      </div>
    </header>

    <main>
      <PostList
        v-if="user"
        :key="user.id"
        @open-modal="openPostModal"
      />
      <div v-else class="welcome">
        <p>Добро пожаловать! Войдите, чтобы увидеть свою ленту.</p>
      </div>
    </main>

    <!-- Модалка поста -->
    <PostModal
      v-if="selectedPost"
      :post="selectedPost"
      @close="selectedPost = null"
    />

    <!-- Модалка авторизации (упрощённая) -->
    <div v-if="showAuth" class="modal-overlay" @click.self="showAuth = false">
      <div class="modal auth-modal">
        <button class="modal-close" @click="showAuth = false">&times;</button>
        <h2>Вход / Регистрация</h2>
        <p>Для демо можно использовать существующего пользователя или создать нового.</p>
        <div style="margin: 20px 0">
          <input v-model="authName" placeholder="Имя пользователя" />
        </div>
        <button @click="handleRegister">Создать и войти</button>
        <div style="margin-top: 15px">
          <small>Уже есть ID? Введите ID:</small>
          <input v-model.number="authId" type="number" placeholder="ID пользователя" style="margin-top: 5px" />
          <button @click="handleLoginById" style="margin-top: 5px">Войти по ID</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import PostList from './components/PostList.vue'
import PostModal from './components/PostModal.vue'
import * as api from './api'

export default {
  components: { PostList, PostModal },
  setup() {
    const user = ref(null)
    const showAuth = ref(false)
    const authName = ref('')
    const authId = ref(null)
    const selectedPost = ref(null)

    async function loadUser() {
      if (!api.getToken()) return
      try {
        user.value = await api.getMe()
      } catch {
        api.setToken(null)
        user.value = null
      }
    }

    async function handleRegister() {
      if (!authName.value) return
      try {
        const { access_token } = await api.createUser(authName.value)
        api.setToken(access_token)
        await loadUser()
        showAuth.value = false
        authName.value = ''
      } catch (err) {
        alert(err.message)
      }
    }

    async function handleLoginById() {
      if (!authId.value) return
      try {
        const { access_token } = await api.getUserToken(authId.value)
        api.setToken(access_token)
        await loadUser()
        showAuth.value = false
        authId.value = null
      } catch (err) {
        alert(err.message)
      }
    }

    function logout() {
      api.setToken(null)
      user.value = null
    }

    function openPostModal(post) {
      selectedPost.value = post
    }

    onMounted(() => {
      loadUser()
    })

    return {
      user,
      showAuth,
      authName,
      authId,
      selectedPost,
      handleRegister,
      handleLoginById,
      logout,
      openPostModal,
    }
  }
}
</script>

<style>
.welcome {
  text-align: center;
  padding: 40px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.auth-modal input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 16px;
}
</style>