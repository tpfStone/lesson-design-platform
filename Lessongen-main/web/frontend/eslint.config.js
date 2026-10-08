import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";
import vueParser from "vue-eslint-parser";

export default [
  { ignores: ["dist/**", "coverage/**", "node_modules/**", "e2e/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  {
    languageOptions: {
      globals: {
        window: "readonly",
        document: "readonly",
        crypto: "readonly",
        sessionStorage: "readonly",
        File: "readonly",
        FormData: "readonly",
        Blob: "readonly",
        Event: "readonly",
        MessageEvent: "readonly",
        EventSource: "readonly",
        DragEvent: "readonly",
        HTMLInputElement: "readonly",
        HTMLDivElement: "readonly",
        matchMedia: "readonly",
        ResizeObserver: "readonly",
      },
    },
  },
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: { parser: tseslint.parser, extraFileExtensions: [".vue"] },
    },
    rules: { "vue/multi-word-component-names": "off" },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        URL: "readonly",
      },
    },
  },
  { rules: { "@typescript-eslint/no-explicit-any": "off" } },
];
