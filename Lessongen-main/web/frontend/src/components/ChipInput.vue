<script setup lang="ts">
import { ref } from "vue";
const model = defineModel<string[]>({ default: () => [] });
withDefaults(defineProps<{ placeholder?: string; ariaLabel?: string }>(), {
  placeholder: "输入后按回车",
  ariaLabel: "条目",
});
const input = ref("");
function add() {
  const value = input.value.trim();
  if (value && !model.value.includes(value))
    model.value = [...model.value, value];
  input.value = "";
}
function remove(index: number) {
  model.value = model.value.filter((_, item) => item !== index);
}
defineExpose({ commitPending: add });
</script>
<template>
  <div class="chip-editor">
    <div v-if="model.length" class="chip-list">
      <span
        v-for="(item, index) in model"
        :key="`${item}-${index}`"
        class="chip"
      >
        {{ item
        }}<button
          type="button"
          :aria-label="`删除${ariaLabel}：${item}`"
          @click="remove(index)"
        >
          ×
        </button>
      </span>
    </div>
    <div class="chip-add">
      <input
        v-model="input"
        :placeholder="placeholder"
        :aria-label="ariaLabel"
        @keydown.enter.prevent="add"
        @blur="add"
      />
      <button type="button" :aria-label="`添加${ariaLabel}`" @click="add">
        添加
      </button>
    </div>
  </div>
</template>
