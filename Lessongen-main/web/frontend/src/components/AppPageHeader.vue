<script setup lang="ts">
defineProps<{ title: string; description?: string; label?: string }>();
</script>

<template>
  <header class="v2-page-header">
    <div class="v2-page-header__text">
      <p v-if="label" class="v2-page-header__label">{{ label }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="v2-page-header__description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="v2-page-header__actions"><slot name="actions" /></div>
  </header>
</template>
