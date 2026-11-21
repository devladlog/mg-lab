// Flat config with type-aware rules. typescript-eslint uses the TypeScript 6.0 API
// ("typescript" in package.json is aliased to @typescript/typescript6), because TypeScript 7.0 ships no API.
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig(
  { ignores: ["dist/**", "node_modules/**", "eslint.config.mjs"] },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // A switch over a union must handle every member (complements assertNever in default branches).
      "@typescript-eslint/switch-exhaustiveness-check": ["error", { considerDefaultExhaustiveForUnions: true }],
      // Numbers in template literals are fine; objects are not.
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
    },
  },
  // demo/ holds code that is wrong on purpose (npm run demo:errors / demo:lint). Keep it out of `npm run lint`.
  { ignores: ["demo/**"] },
);
