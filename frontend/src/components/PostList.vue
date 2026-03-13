<template>
  <div class="post-list" ref="scrollContainer">
    <div
      v-for="post in posts"
      :key="post.id"
      class="post-card"
      @click="$emit('open-modal', post)"
    >
      <h3>{{ post.title }}</h3>
      <p>{{ post.text }}</p>
      <small>{{ new Date(post.created_at).toLocaleString() }}</small>
    </div>

    <div v-if="loading" class="loader">Загрузка...</div>
    <div v-if="!hasMore && posts.length > 0" class="end-message">
      Больше нет публикаций
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import * as api from '../api'

export default {
  emits: ['open-modal'],
  setup() {
    const posts = ref([])
    const loading = ref(false)
    const hasMore = ref(true)
    const offset = ref(0)
    const limit = 10
    const scrollContainer = ref(null)

    async function loadPosts() {
      if (loading.value || !hasMore.value) return
      loading.value = true
      try {
        const newPosts = await api.getMyPosts(limit, offset.value)
        if (newPosts.length < limit) {
          hasMore.value = false
        }
        posts.value = [...posts.value, ...newPosts]
        offset.value += newPosts.length
      } catch (err) {
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    function handleScroll() {
      const el = scrollContainer.value
      if (!el) return
      const scrollBottom = el.scrollTop + el.clientHeight
      const threshold = el.scrollHeight - 500
      if (scrollBottom >= threshold) {
        loadPosts()
      }
    }

    onMounted(() => {
      loadPosts()
      const el = scrollContainer.value
      if (el) {
        el.addEventListener('scroll', handleScroll)
      }
    })

    onUnmounted(() => {
      const el = scrollContainer.value
      if (el) {
        el.removeEventListener('scroll', handleScroll)
      }
    })

    return {
      posts,
      loading,
      hasMore,
      scrollContainer,
    }
  }
}
</script>
