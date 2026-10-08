<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ content: string; title?: string }>();
type Block = { type: "title" | "heading" | "subheading" | "paragraph" | "list" | "quote" | "table"; text?: string; rows?: string[][] };
const clean = (value: string) => value.replace(/<br\s*\/?\s*>/gi, "\n").replace(/\*\*(.*?)\*\*/g, "$1").replace(/`([^`]*)`/g, "$1").trim();
function tableCells(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map(cell => clean(cell.replace(/\\\|/g, "|")));
}
const blocks = computed<Block[]>(() => {
  const lines = props.content.replace(/\r\n?/g, "\n").split("\n");
  const result: Block[] = [];
  let paragraph: string[] = [];
  function flush() { if (paragraph.length) { result.push({ type: "paragraph", text: clean(paragraph.join("\n")) }); paragraph = []; } }
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index].trim();
    if (!line) { flush(); continue; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) { flush(); result.push({ type: heading[1].length === 1 ? "title" : heading[1].length === 2 ? "heading" : "subheading", text: clean(heading[2]) }); continue; }
    if (line.startsWith("|") && line.endsWith("|")) {
      flush(); const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().startsWith("|") && lines[index].trim().endsWith("|")) {
        const cells = tableCells(lines[index]);
        if (!cells.every(cell => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        index++;
      }
      index--;
      if (rows.length) result.push({ type: "table", rows });
      continue;
    }
    if (/^[-*]\s+/.test(line) || /^\d+[.、]\s*/.test(line)) { flush(); result.push({ type: "list", text: clean(line.replace(/^([-*]\s+|\d+[.、]\s*)/, "")) }); continue; }
    if (line.startsWith(">")) {
      flush();
      const quote = clean(line.replace(/^>\s*/, ""));
      if (!/^运行\s/.test(quote)) result.push({ type: "quote", text: quote });
      continue;
    }
    if (/^[一二三四五六七八九十]+[、．.]\s*[^。]{1,28}$/.test(line)) {
      flush(); result.push({ type: "heading", text: clean(line) }); continue;
    }
    paragraph.push(line);
  }
  flush();
  return result;
});
</script>
<template>
  <article class="review-paper" aria-label="教案正文预览">
    <header v-if="title" class="review-paper-header"><small>教案预览</small><h3>{{ title }}</h3></header>
    <template v-for="(block, index) in blocks" :key="index">
      <h3 v-if="block.type === 'title'" class="paper-title">{{ block.text }}</h3>
      <h4 v-else-if="block.type === 'heading'" class="paper-heading"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ block.text }}</h4>
      <h5 v-else-if="block.type === 'subheading'" class="paper-subheading">{{ block.text }}</h5>
      <p v-else-if="block.type === 'paragraph'">{{ block.text }}</p>
      <p v-else-if="block.type === 'list'" class="paper-list">{{ block.text }}</p>
      <blockquote v-else-if="block.type === 'quote'">{{ block.text }}</blockquote>
      <div v-else-if="block.type === 'table'" class="table-scroll"><table><thead><tr><th v-for="(cell, n) in block.rows?.[0]" :key="n">{{ cell }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in block.rows?.slice(1)" :key="rowIndex"><td v-for="(cell, n) in row" :key="n">{{ cell }}</td></tr></tbody></table></div>
    </template>
  </article>
</template>
<style scoped>
.review-paper { padding:clamp(20px,3vw,36px); background:#fffefa; color:#1d3150; font-family:'Noto Serif SC','Songti SC',serif; overflow-wrap:anywhere; line-height:1.85; }
.review-paper-header { border-bottom:2px solid #253b5c; margin-bottom:26px; padding-bottom:22px; text-align:center; }.review-paper-header small { color:#3166d8; font:700 12px system-ui,sans-serif; letter-spacing:.12em; }.review-paper-header h3 { font-size:clamp(21px,3vw,28px); line-height:1.4; margin:10px 0 0; }
.paper-title { margin:12px 0 24px; font-size:clamp(22px,3vw,29px); text-align:center; line-height:1.5; }.paper-heading { display:flex; align-items:baseline; gap:14px; margin:28px 0 12px; padding-top:19px; border-top:1px solid #e6e3db; font-size:20px; }.paper-heading span { color:#627da5; font:700 13px system-ui,sans-serif; }.paper-subheading { font-size:17px; margin:18px 0 8px; }.review-paper p { font-size:15px; white-space:pre-wrap; margin:12px 0; }.paper-list { padding:11px 14px 11px 32px; border-radius:9px; background:#f4f7fc; position:relative; }.paper-list::before { content:'•'; position:absolute; left:15px; color:#3166d8; }.review-paper blockquote { padding:12px 16px; border-left:3px solid #4d78d7; color:#587087; background:#f4f7fc; font-size:13px; }.table-scroll { overflow:auto; margin:16px 0; border:1px solid #dce5f2; border-radius:9px; }.review-paper table { width:100%; border-collapse:collapse; font-size:14px; line-height:1.65; }.review-paper th,.review-paper td { padding:10px 12px; text-align:left; vertical-align:top; border-bottom:1px solid #e3e9f2; min-width:100px; white-space:pre-line; }.review-paper th { background:#f0f5ff; color:#244d9c; }.review-paper tr:last-child td { border-bottom:0; }
</style>
