<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { ElAlert, ElButton, ElTag, ElProgress, ElSelect, ElOption, ElLoading } from "element-plus";
import "element-plus/dist/index.css";
import AppPageHeader from "../components/AppPageHeader.vue";
import NavigationTransferPanel from "../components/NavigationTransferPanel.vue";
import ResultDownloadPanel, { type DownloadFile } from "../components/ResultDownloadPanel.vue";
import { request, type NavigationState } from "../features/navigation/api";

const vLoading = ElLoading.directive;
const route = useRoute();
const router = useRouter();
const queryId = () => typeof route.query.session === "string" ? route.query.session : "";
const storagePrefix = "platform.f4.";
const state = ref<NavigationState | null>(null);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const booting = ref(true);
const savedId = ref(queryId() || localStorage.getItem(storagePrefix + "session") || "");
const selectedVersion = ref<number | null>(null);
let disposed = false;

onBeforeUnmount(() => { disposed = true; });

const current = computed(() => state.value?.sections.find(section => section.id === state.value?.session.current_section_id));
const status = computed(() => state.value?.session.status);
const maxRounds = computed(() => state.value?.session.config_snapshot.max_rounds || 5);
const completed = computed(() => state.value?.sections.filter(section => section.review.completed_at).length || 0);
const canNext = computed(() => Boolean(current.value?.review.generated_at && current.value.suggestions.every(suggestion => suggestion.decision)));
const path = computed(() => "/sessions/" + state.value?.session.id);
const finalContent = computed(() => (selectedVersion.value === null
  ? state.value?.lesson_plan.current_content
  : state.value?.lesson_plan_versions.find(version => version.round_number === selectedVersion.value)?.content) || "");
const currentFinalContent = computed(() => state.value?.lesson_plan.current_content || "");
const stage = computed(() => !state.value ? 0 : status.value === "ACTIVE" ? 1 : status.value === "ROUND_COMPLETED" ? 2 : 3);
const statusText = computed(() => status.value === "TERMINATED" ? "已完成" : status.value === "ROUND_COMPLETED" ? "本轮已完成" : "正在共析");
const acceptedCount = computed(() => state.value?.sections.reduce((sum, section) => sum + section.suggestions.filter(item => item.decision?.decision === "ACCEPT").length, 0) || 0);
const rejectedCount = computed(() => state.value?.sections.reduce((sum, section) => sum + section.suggestions.filter(item => item.decision?.decision === "REJECT").length, 0) || 0);

function target() {
  if (!state.value || !current.value) throw new Error("当前没有可共析的教学单元，请恢复最新状态。");
  return { round_id: state.value.round.id, section_id: current.value.id };
}

function persistState(data: NavigationState) {
  state.value = data;
  savedId.value = data.session.id;
  localStorage.setItem(storagePrefix + "session", data.session.id);
  if (!disposed && queryId() !== data.session.id) {
    const query: Record<string, string> = { session: data.session.id };
    if (route.query.workflow === "1") query.workflow = "1";
    void router.replace({ path: "/platform/navigation", query });
  }
}

async function logView() {
  if (!current.value || disposed) return;
  await nextTick();
  if (!current.value || disposed) return;
  try {
    await request(path.value + "/view", {
      ...target(),
      section_version_id: current.value.version.id,
      suggestion_ids: current.value.suggestions.map(suggestion => suggestion.id),
      decision_ids: current.value.suggestions.filter(suggestion => suggestion.decision).map(suggestion => suggestion.decision!.id),
    });
  } catch {
    notice.value = "当前正文与选择已恢复；查看记录暂未写入，不影响继续共析。";
  }
}

async function run(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try { await action(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { busy.value = false; }
}

async function recover(id = savedId.value) {
  if (!id.trim()) return;
  await run(async () => {
    persistState(await request<NavigationState>("/sessions/" + encodeURIComponent(id.trim()) + "/current-state"));
    selectedVersion.value = null;
    await logView();
  });
}

async function mutate(suffix: string, body: unknown = {}) {
  await run(async () => {
    persistState(await request<NavigationState>(path.value + suffix, body));
    selectedVersion.value = null;
    await logView();
  });
}

function startNewSession() {
  if (busy.value) return;
  state.value = null;
  selectedVersion.value = null;
  error.value = "";
  notice.value = "";
  savedId.value = "";
  localStorage.removeItem(storagePrefix + "session");
  const query = route.query.workflow === "1" ? { workflow: "1" } : {};
  void router.push({ path: "/navigation", query });
}

function reportText() {
  if (!state.value) return "";
  const lines: string[] = [
    "协同共析建议摘要",
    `课题：${state.value.session.lesson_metadata.topic}`,
    `轮次：第 ${state.value.round.round_number} 轮`,
    "",
  ];
  for (const section of state.value.sections) {
    lines.push(`【${section.title}】`);
    if (!section.suggestions.length) {
      lines.push("暂无新增建议。", "");
      continue;
    }
    section.suggestions.forEach((suggestion, index) => {
      const decision = suggestion.decision?.decision === "ACCEPT" ? "已采纳" : suggestion.decision?.decision === "REJECT" ? "已保留原稿" : "未决定";
      lines.push(
        `${index + 1}. ${suggestion.issue}`,
        `处理状态：${decision}`,
        `原因：${suggestion.reason}`,
        `建议：${suggestion.revision}`,
        "",
      );
    });
  }
  return lines.join("\n");
}

function textHref(content: string) {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`;
}

const resultFiles = computed<DownloadFile[]>(() => {
  if (!state.value || status.value !== "TERMINATED") return [];
  return [
    {
      key: "lesson",
      label: "修订后的教案",
      href: textHref(currentFinalContent.value),
      filename: "协同共析-修订教案.txt",
    },
    {
      key: "suggestions",
      label: "共析建议摘要",
      href: textHref(reportText()),
      filename: "协同共析-建议摘要.txt",
    },
  ];
});

watch(() => route.query.session, id => {
  if (typeof id === "string" && id !== state.value?.session.id && !booting.value && !busy.value) void recover(id);
});

onMounted(async () => {
  if (savedId.value) await recover();
  booting.value = false;
});
</script>

<template>
  <div class="navigation-workbench f4-workbench">
    <AppPageHeader
      title="协同共析"
      description="逐节查看建议、判断取舍并保留修订过程。每一次采纳或保留都会立即记录，刷新后可继续当前进度。"
    >
      <template #actions>
        <el-button v-if="state" :disabled="busy" @click="recover()">刷新当前进度</el-button>
      </template>
    </AppPageHeader>

    <div class="workspace-body" v-loading="booting">
      <el-alert
        v-if="error"
        class="f4-alert"
        type="error"
        :title="error"
        show-icon
        :closable="false"
      >
        <el-button v-if="savedId" text :disabled="busy" @click="recover()">恢复最新状态</el-button>
      </el-alert>
      <el-alert v-if="notice" class="f4-alert" :title="notice" type="warning" :closable="false" />

      <section v-if="!state && !booting" class="empty-workbench v2-card">
        <span class="empty-mark">析</span>
        <div>
          <h2>还没有开始协同共析</h2>
          <p>先选择一份已有教案和版本，再进入逐节共析工作台。</p>
          <RouterLink class="v2-button v2-button--primary" :to="{ path: '/navigation', query: route.query.workflow === '1' ? { workflow: '1' } : {} }">选择教案</RouterLink>
        </div>
      </section>

      <template v-else-if="state">
        <section class="session-overview v2-card">
          <div class="session-copy">
            <small>当前教案</small>
            <h2>{{ state.session.lesson_metadata.topic }}</h2>
            <p>{{ state.session.lesson_metadata.subject }} · {{ state.session.lesson_metadata.grade }} · 第 {{ state.round.round_number }} / {{ maxRounds }} 轮</p>
          </div>
          <div class="session-stats" aria-label="共析状态">
            <span class="status-chip">{{ statusText }}</span>
            <span>{{ completed }}/{{ state.sections.length }} 单元</span>
            <span>{{ acceptedCount }} 条采纳</span>
            <span>{{ rejectedCount }} 条保留</span>
          </div>
        </section>

        <nav class="f4-stage-bar" aria-label="协同共析进度">
          <div v-for="(label, index) in ['准备教案', '逐节共析', '轮次回顾', '完成修订']" :key="label" :class="{ active: stage === index, done: stage > index }">
            <span>{{ stage > index ? "✓" : index + 1 }}</span><strong>{{ label }}</strong>
          </div>
        </nav>

        <div v-if="status === 'ACTIVE' && current" class="review-layout">
          <aside class="section-nav v2-card">
            <div class="section-nav-heading">
              <div><small>教学单元</small><strong>逐节共析</strong></div>
              <span>{{ completed }} / {{ state.sections.length }}</span>
            </div>
            <el-progress :percentage="Math.round((completed / state.sections.length) * 100)" :show-text="false" />
            <ol>
              <li
                v-for="(section, index) in state.sections"
                :key="section.id"
                :class="{ selected: section.id === current.id, completed: section.review.completed_at }"
              >
                <span>{{ section.review.completed_at ? "✓" : index + 1 }}</span>
                <span>{{ section.title }}</span>
              </li>
            </ol>
            <p>按顺序完成每个单元，已完成的决定会自动保存。</p>
          </aside>

          <div class="review-main">
            <section class="lesson-section v2-card">
              <div class="section-heading">
                <div>
                  <small>当前单元 {{ current.order_index + 1 }} / {{ state.sections.length }}</small>
                  <h2>{{ current.title }}</h2>
                </div>
                <el-tag type="info" effect="plain">当前版本 V{{ current.version.version_number }}</el-tag>
              </div>
              <pre class="lesson-text">{{ current.current_content }}</pre>
            </section>

            <section class="feedback-area">
              <div class="feedback-heading">
                <div><small>共析建议</small><h2>针对当前单元的修改意见</h2></div>
                <el-tag v-if="current.review.generated_at" type="info" effect="plain">{{ current.suggestions.length }} 条</el-tag>
              </div>

              <div v-if="!current.review.generated_at" class="generate-box v2-card">
                <div>
                  <h3>生成当前单元建议</h3>
                  <p>系统会结合当前教案内容给出少量建议，最终是否采纳由你决定。</p>
                </div>
                <el-button type="primary" :loading="busy" @click="mutate('/suggestions', target())">生成共析建议</el-button>
              </div>

              <div v-else-if="!current.suggestions.length" class="empty-suggestions v2-card">
                <strong>本单元暂无新增建议</strong>
                <p>可以保留当前内容并继续下一个单元。</p>
              </div>

              <article
                v-for="(suggestion, index) in current.suggestions"
                :key="suggestion.id"
                class="suggestion-card v2-card"
                :class="{ decided: suggestion.decision }"
              >
                <div class="suggestion-title">
                  <span>建议 {{ index + 1 }}</span>
                  <el-tag v-if="suggestion.decision" :type="suggestion.decision.decision === 'ACCEPT' ? 'primary' : 'info'" effect="plain">
                    {{ suggestion.decision.decision === "ACCEPT" ? "已采纳" : "已保留原稿" }}
                  </el-tag>
                </div>
                <h3>{{ suggestion.issue }}</h3>
                <dl>
                  <dt>为什么值得关注</dt>
                  <dd>{{ suggestion.reason }}</dd>
                  <dt>教学依据 <span class="basis-state">{{ suggestion.basis_type === 'verified_source' ? '已核验资料' : '建议教师复核' }}</span></dt>
                  <dd>{{ suggestion.pedagogical_basis }}</dd>
                  <dd v-for="source in suggestion.basis_sources || []" :key="source.id" class="source-note">
                    <strong>{{ source.source }} · {{ source.source_locator }}</strong><br />{{ source.content }}
                  </dd>
                  <dt>{{ suggestion.revision_mode === 'replace' ? '建议修改为' : '建议补充' }}</dt>
                  <dd v-if="suggestion.target_text" class="target-text">对应原文：{{ suggestion.target_text }}</dd>
                  <dd class="revision-text">{{ suggestion.revision }}</dd>
                </dl>

                <div v-if="!suggestion.decision" class="decision-actions">
                  <el-button type="primary" :disabled="busy" @click="mutate('/suggestions/' + suggestion.id + '/decision', { decision: 'ACCEPT' })">采纳建议</el-button>
                  <el-button :disabled="busy" @click="mutate('/suggestions/' + suggestion.id + '/decision', { decision: 'REJECT' })">保留原稿</el-button>
                  <span>{{ suggestion.revision_mode === 'replace' ? '采纳后仅在定位明确时替换正文' : '采纳后补充到当前单元' }}</span>
                </div>

                <div v-if="state.revision_candidate?.suggestion_id === suggestion.id && !suggestion.decision" class="candidate-box">
                  <strong>需要你确认补充方式</strong>
                  <p>{{ state.revision_candidate.reason }}</p>
                  <pre class="lesson-text">{{ state.revision_candidate.candidate }}</pre>
                  <el-button :disabled="busy" @click="mutate('/suggestions/' + suggestion.id + '/decision', { decision: 'ACCEPT', confirm_append: true, expected_version_id: state.revision_candidate.expected_version_id })">作为补充采纳（保留原文）</el-button>
                </div>
              </article>
            </section>

            <div class="next-bar">
              <p>{{ canNext ? "当前单元的选择已经保存，可以继续。" : "生成建议后，请先完成每条建议的取舍。" }}</p>
              <el-button type="primary" size="large" :disabled="!canNext || busy" @click="mutate('/complete-section', target())">
                {{ current.order_index + 1 === state.sections.length ? "完成本轮" : "进入下一单元" }}
              </el-button>
            </div>
          </div>
        </div>

        <section v-if="status === 'ROUND_COMPLETED'" class="round-complete v2-card">
          <span class="complete-icon">✓</span>
          <small>第 {{ state.round.round_number }} 轮完成</small>
          <h2>本轮共析结果已经保存</h2>
          <p>{{ state.sections.length }} 个教学单元均已完成查看和取舍。你可以继续下一轮，也可以结束本次共析。</p>
          <div class="round-actions">
            <el-button size="large" :disabled="busy" @click="mutate('/terminate')">结束本次共析</el-button>
            <el-button v-if="state.round.round_number < maxRounds" type="primary" size="large" :disabled="busy" @click="mutate('/rounds/' + state.round.id + '/continue')">继续下一轮</el-button>
          </div>
        </section>

        <section v-if="status === 'ROUND_COMPLETED' || status === 'TERMINATED'" class="final-panel v2-card">
          <div class="section-heading">
            <div>
              <small>{{ status === "TERMINATED" ? "共析完成" : "本轮结果" }}</small>
              <h2>{{ status === "TERMINATED" ? "最终修订教案" : "本轮修订教案" }}</h2>
            </div>
            <el-select v-model="selectedVersion" clearable placeholder="当前最新版" aria-label="查看修订轮次" style="width:190px">
              <el-option v-for="version in state.lesson_plan_versions" :key="version.id" :value="version.round_number" :label="version.round_number === 0 ? 'V0 · 原始教案' : `V${version.round_number} · 第 ${version.round_number} 轮`" />
            </el-select>
          </div>
          <pre class="lesson-text final-text">{{ finalContent }}</pre>
        </section>

        <NavigationTransferPanel v-if="status === 'ROUND_COMPLETED' || status === 'TERMINATED'" :state="state" :disabled="busy" />

        <ResultDownloadPanel
          v-if="status === 'TERMINATED'"
          :files="resultFiles"
          description="本次协同共析已经完成，可下载最终修订稿和教师可读的建议摘要。"
        />

        <div v-if="status === 'TERMINATED' && route.query.workflow !== '1'" class="finished-actions">
          <el-button @click="startNewSession">开始新的协同共析</el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped src="../styles/navigation-workbench.css"></style>
