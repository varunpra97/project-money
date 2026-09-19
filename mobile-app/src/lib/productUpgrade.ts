export interface ProductUpgrade { id: string; title: string; detail: string; measure: string; }
export function upgradePrompt(idea: ProductUpgrade) {
  return `Implement this approved Pulse product upgrade in the web and iPhone apps where applicable. Inspect existing code, preserve unrelated work, run relevant checks, and report the changes and any deployment steps. Native changes require a signed Xcode build.\n\nUpgrade: ${idea.title}\nScope: ${idea.detail}\nEvaluation: ${idea.measure}`;
}
