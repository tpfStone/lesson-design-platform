const labels: Record<string, string> = {
  metadata: "课程信息",
  subject: "科目",
  grade: "年级",
  topic: "课题",
  duration_minutes: "课时",
  textbook_version: "教材版本",
  design_thesis: "设计主张",
  driving_question: "核心问题",
  learning_trajectory: "学习路径",
  curriculum_standards: "课程标准",
  content_analysis: "内容分析",
  student_analysis: "学情分析",
  learning_objectives: "学习目标",
  description: "目标描述",
  evidence_of_achievement: "达成证据",
  key_points: "教学重点",
  difficult_points: "教学难点",
  teaching_strategy: "教学策略",
  resources: "教学资源",
  teaching_artifacts: "学生作品与材料",
  procedure_steps: "教学过程",
  stage: "环节",
  duration: "时间",
  teacher_actions: "教师活动",
  student_actions: "学生活动",
  questions: "课堂提问",
  question: "问题",
  assessment: "观察与评价",
  assessment_plan: "评价设计",
  differentiation: "差异化支持",
  homework: "作业设计",
  board_design: "板书设计",
  reflection: "课后反思",
  references: "参考资料",
  template_extensions: "补充内容",
};
const hiddenKeys = new Set([
  "schema_version",
  "plan_id",
  "task_id",
  "template_id",
  "step_id",
  "objective_id",
  "resource_id",
  "artifact_id",
]);

export function lessonPathLabel(path: string): string {
  if (!path.startsWith("/")) return "教案整体";
  const parts = path
    .split("/")
    .slice(1)
    .map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"));
  if (!parts.length) return "教案整体";
  return parts
    .map((part, index) => {
      if (/^\d+$/.test(part))
        return parts[0] === "procedure_steps"
          ? `第 ${Number(part) + 1} 环节`
          : `第 ${Number(part) + 1} 项`;
      return labels[part] || (index === 0 ? "其他教案内容" : part);
    })
    .join(" · ");
}

export function formatTeachingContent(value: unknown): string {
  if (value == null || value === "") return "（未填写）";
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) {
    if (!value.length) return "（未填写）";
    return value
      .map((item, index) => `${index + 1}. ${formatTeachingContent(item)}`)
      .join("\n");
  }
  if (typeof value === "object") {
    const lines = Object.entries(value)
      .filter(([key]) => !hiddenKeys.has(key))
      .map(([key, content]) => {
        const formatted = formatTeachingContent(content);
        return `${labels[key] || key}：${formatted}`;
      });
    return lines.length ? lines.join("\n") : "（无可展示内容）";
  }
  return "（无可展示内容）";
}
