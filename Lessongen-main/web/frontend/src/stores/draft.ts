import { defineStore } from "pinia";
import type { LessonInput, OptimizeInput } from "../types/api";

const base = (): LessonInput => ({
  subject: "",
  grade: "",
  topic: "",
  durationMinutes: 45,
  courseInformation: "",
  textbookVersion: "",
  textbookContent: "",
  curriculumStandards: [],
  learningObjectives: [],
  studentProfile: "",
  classSize: null,
  availableResources: [],
  additionalRequirements: "",
  lessonStyle: "choose_the_best_fit_for_this_topic",
  detailLevel: "showcase",
});
const load = <T>(key: string, fallback: T): T => {
  try {
    return JSON.parse(sessionStorage.getItem(key) || "") as T;
  } catch {
    return fallback;
  }
};

export const useDraftStore = defineStore("draft", {
  state: () => ({
    generate: load<LessonInput>("lesoongen.generate-draft", base()),
    optimize: load<OptimizeInput>("lesoongen.optimize-draft", {
      ...base(),
      optimizationFocus: [],
      mustPreserveContent: [],
    }),
  }),
  actions: {
    persistGenerate() {
      try {
        sessionStorage.setItem(
          "lesoongen.generate-draft",
          JSON.stringify(this.generate),
        );
        return true;
      } catch {
        return false;
      }
    },
    persistOptimize() {
      try {
        sessionStorage.setItem(
          "lesoongen.optimize-draft",
          JSON.stringify(this.optimize),
        );
        return true;
      } catch {
        return false;
      }
    },
    clearGenerate() {
      this.generate = base();
      try {
        sessionStorage.removeItem("lesoongen.generate-draft");
      } catch {
        // The in-memory draft is still cleared when storage is unavailable.
      }
    },
    clearOptimize() {
      this.optimize = {
        ...base(),
        optimizationFocus: [],
        mustPreserveContent: [],
      };
      try {
        sessionStorage.removeItem("lesoongen.optimize-draft");
      } catch {
        // The in-memory draft is still cleared when storage is unavailable.
      }
    },
  },
});
