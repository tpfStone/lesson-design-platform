<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";

interface SectionItem {
  id: string;
  label: string;
  state: string;
  complete?: boolean;
}
const props = defineProps<{ items: SectionItem[]; note: string }>();
const activeId = ref(props.items[0]?.id ?? "");
const activeIndex = computed(() =>
  Math.max(
    0,
    props.items.findIndex((item) => item.id === activeId.value),
  ),
);
const nextItem = computed(() => props.items[activeIndex.value + 1]);
const nav = ref<globalThis.HTMLElement>();
let frame = 0;

function refresh() {
  frame = 0;
  const edge = window.innerWidth <= 760 ? 164 : 176;
  const current = props.items
    .filter((item) => {
      const section = document.getElementById(item.id);
      return section && section.getBoundingClientRect().top <= edge;
    })
    .at(-1);
  activeId.value = current?.id ?? props.items[0]?.id ?? "";
}
function scheduleRefresh() {
  if (!frame) frame = window.requestAnimationFrame(refresh);
}
function navigate(id: string) {
  const section = document.getElementById(id);
  if (section instanceof window.HTMLDetailsElement) section.open = true;
  activeId.value = id;
}
watch(activeId, async () => {
  await nextTick();
  const link = Array.from(nav.value?.querySelectorAll("a") ?? []).find(
    (item) => item.getAttribute("href") === `#${activeId.value}`,
  );
  if (!link || !nav.value) return;
  nav.value.scrollTo({
    left:
      (link as globalThis.HTMLElement).offsetLeft -
      nav.value.offsetLeft -
      (nav.value.clientWidth - (link as globalThis.HTMLElement).clientWidth) /
        2,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
  });
});
onMounted(() => {
  void nextTick(refresh);
  window.addEventListener("scroll", scheduleRefresh, { passive: true });
  window.addEventListener("resize", scheduleRefresh);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", scheduleRefresh);
  window.removeEventListener("resize", scheduleRefresh);
  if (frame) window.cancelAnimationFrame(frame);
});
</script>

<template>
  <div class="wayfinder-wrap">
    <div class="wayfinder-summary">
      <span
        >第 {{ activeIndex + 1 }} / {{ items.length }} 部分 ·
        {{ items[activeIndex]?.label }}</span
      >
      <a
        v-if="nextItem"
        class="wayfinder-next"
        :href="`#${nextItem.id}`"
        @click="navigate(nextItem.id)"
        >下一部分 <span aria-hidden="true">→</span></a
      >
    </div>
    <nav ref="nav" class="form-wayfinder" aria-label="表单填写路线">
      <a
        v-for="(item, index) in items"
        :key="item.id"
        :href="`#${item.id}`"
        :aria-current="activeId === item.id ? 'location' : undefined"
        :class="{ complete: item.complete }"
        @click="navigate(item.id)"
      >
        <span aria-hidden="true">{{ item.complete ? "✓" : index + 1 }}</span>
        <span
          >{{ item.label }}<small>{{ item.state }}</small></span
        >
      </a>
    </nav>
    <p class="wayfinder-note">{{ note }}</p>
  </div>
</template>
