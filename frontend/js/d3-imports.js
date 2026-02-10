/**
 * d3-imports.js — Shared D3 import for all modules.
 * Uses dynamic import with top-level await (supported in ES modules).
 */
const d3 = await import('https://cdn.jsdelivr.net/npm/d3@7/+esm');
export default d3;
