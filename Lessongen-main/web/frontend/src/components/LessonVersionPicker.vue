<script setup lang="ts">
import LessonSelectorBar, { type LessonOption, type VersionOption } from "./LessonSelectorBar.vue";
withDefaults(defineProps<{ initialLessonId?: string; initialVersionId?: string; showTools?: boolean }>(), {
  initialLessonId: "", initialVersionId: "", showTools: true,
});
const emit = defineEmits<{ selection: [lesson: LessonOption | null, version: VersionOption | null] }>();
</script>
<template>
  <LessonSelectorBar :initial-lesson-id="initialLessonId" :initial-version-id="initialVersionId" :show-tools="showTools" @selection="(lesson, version) => emit('selection', lesson, version)" />
</template>
