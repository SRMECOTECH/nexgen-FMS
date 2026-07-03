// The Route Intelligence pages and AIAssistant are plain .jsx (no types).
// This shim lets `tsc -b` accept them so `npm run build` works on a fresh clone.
declare module '*.jsx';
