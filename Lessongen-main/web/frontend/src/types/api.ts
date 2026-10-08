export type JobMode = "GENERATE" | "OPTIMIZE";
export type JobStatus =
  | "QUEUED"
  | "DISPATCHING"
  | "PREPROCESSING"
  | "RUNNING"
  | "EXPORTING"
  | "COMPLETED"
  | "NEEDS_HUMAN"
  | "FAILED";

export interface LessonInput {
  subject: string;
  grade: string;
  topic: string;
  durationMinutes: number;
  courseInformation?: string;
  textbookVersion?: string;
  textbookContent?: string;
  curriculumStandards?: string[];
  learningObjectives?: string[];
  studentProfile?: string;
  classSize?: number | null;
  availableResources?: string[];
  additionalRequirements?: string;
  lessonStyle?: string;
  detailLevel?: string;
  retryOfJobId?: string;
}

export interface OptimizeInput extends LessonInput {
  optimizationFocus?: string[];
  mustPreserveContent?: string[];
}

export interface JobLinks {
  self: string;
  events: string;
  result: string;
  artifacts: string;
}
export interface JobAccepted {
  jobId: string;
  status: JobStatus;
  createdAt: string;
  links: JobLinks;
}
export interface JobSummary {
  jobId: string;
  mode: JobMode;
  status: JobStatus;
  subject: string;
  grade: string;
  topic: string;
  currentStage: string;
  currentRound: number;
  progressPercent: number;
  createdAt: string;
  finishedAt?: string | null;
}
export interface JobPage {
  items: JobSummary[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
export interface JobUsage {
  modelCallCount: number;
  inputTokens: number;
  outputTokens: number;
  estimatedCost: number;
}
export interface JobDetail extends JobSummary {
  durationMinutes: number;
  pipelineStatus?: string | null;
  stopReason?: string | null;
  bestVersionId?: string | null;
  lastVersionId?: string | null;
  errorCode?: string | null;
  errorMessage?: string | null;
  usage: JobUsage;
  startedAt?: string | null;
  updatedAt: string;
  links: JobLinks;
}
export interface JobEvent {
  sequence: number;
  eventType: string;
  stage: string;
  roundIndex?: number | null;
  versionId?: string | null;
  progressPercent: number;
  message: string;
  occurredAt: string;
}
export interface Artifact {
  artifactId: string;
  type: string;
  displayName: string;
  mediaType: string;
  sizeBytes: number;
  sha256: string;
  downloadUrl: string;
}
export interface LessonResult {
  jobId: string;
  status: JobStatus;
  stopReason?: string | null;
  bestVersionId?: string | null;
  lastVersionId?: string | null;
  bestLessonPlan: Record<string, unknown>;
  scores: Record<string, number>;
  overallScore?: number | null;
  scoreNotice: string;
  optimization?: OptimizationSummary | null;
  review?: {
    policy: string;
    reviewed_roles: string[];
    validator_completed: boolean;
    independent_review_complete: boolean;
    content_changed: boolean;
  } | null;
  changes: Array<{
    summary: string;
    targetPath: string;
    sourceCritiqueIds: string[];
  }>;
  unresolvedIssues: string[];
  parseWarnings: string[];
}
export interface OptimizationSummary {
  outcome:
    | "changed"
    | "revisions_not_selected"
    | "reviewed_unchanged"
    | "not_reviewed"
    | "rewrite_failed";
  message: string;
  baseline_version_id: string;
  selected_version_id: string;
  content_changed: boolean;
  changed_section_count: number;
  changed_sections: Array<{
    field: string;
    label: string;
    before: unknown;
    after: unknown;
  }>;
  unselected_candidate_version_id?: string | null;
  unselected_candidate_score?: number | null;
  unselected_candidate_changed_sections?: Array<{
    field: string;
    label: string;
    before: unknown;
    after: unknown;
  }>;
  baseline_score: number | null;
  selected_score: number | null;
  score_delta: number | null;
  score_notice: string;
  critique_count: number;
  reviewed_issues: Array<{
    critique_id: string;
    role: string;
    target_path: string;
    issue: string;
    suggestion: string;
    status: string;
    decision: string | null;
    decision_reason: string | null;
  }>;
  validation_batch_count: number;
  rewrite_count: number;
  rounds: Array<{
    input_version_id: string;
    output_version_id: string;
    strategy?: "targeted_patch" | "full_document" | "legacy_unknown";
    accepted_count: number;
    implemented_count: number;
    unresolved_count: number;
    unresolved_reasons?: Record<string, string>;
    changes: Array<{
      critique_id: string;
      target_path: string;
      edited_paths?: string[];
      before_summary: string;
      after_summary: string;
    }>;
  }>;
  stop_reason: string | null;
  quality_gate?: {
    passed: boolean;
    content_changed: boolean;
    score_gain: number | null;
    dimension_drops: Record<string, number>;
    hard_rules_ok: boolean;
    no_high_risk: boolean;
    absolute_target_met: boolean;
    relative_target_met: boolean;
    thresholds: {
      overall: number;
      minimum_dimension: number;
      minimum_gain: number;
      maximum_dimension_drop: number;
    };
    note: string;
  } | null;
  pairwise_comparison?: {
    baseline_version_id: string;
    candidate_version_id: string;
    verdict: "candidate_preferred" | "baseline_preferred" | "uncertain";
    target_issue_progress: "improved" | "unchanged" | "worse" | "uncertain";
    changed_sections: string[];
    regression_flags: string[];
    evidence: string[];
    votes?: Array<{ order: string; preference: string }>;
    failed_calls: number;
    reason: string;
  } | null;
}
export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  code?: string;
}

export const terminalStatuses: JobStatus[] = [
  "COMPLETED",
  "NEEDS_HUMAN",
  "FAILED",
];
