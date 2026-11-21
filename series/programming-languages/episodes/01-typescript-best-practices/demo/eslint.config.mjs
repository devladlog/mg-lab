// Same rules as the project, applied to demo/lint-me.ts only.
import base from "../eslint.config.mjs";
export default base.filter((c) => !(c.ignores && c.ignores.includes("demo/**")));
