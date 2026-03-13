<template>
  <Transition name="fade">
    <div v-if="post" class="modal-overlay" @click.self="$emit('close')">
      <Transition name="slide">
        <div class="modal">
          <button class="modal-close" @click="$emit('close')">&times;</button>
          <h2>{{ post.title }}</h2>
          <p>{{ post.text }}</p>
          <div class="meta">
            <div>Автор: {{ post.user_id }}</div>
            <div>Создано: {{ new Date(post.created_at).toLocaleString() }}</div>
            <div v-if="post.updated_at !== post.created_at">
              Обновлено: {{ new Date(post.updated_at).toLocaleString() }}
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
</template>

<script>
export default {
  props: {
    post: Object,
  },
  emits: ['close'],
}
</script>