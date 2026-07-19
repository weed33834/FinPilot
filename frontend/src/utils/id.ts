export function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID()
    } catch {
      // fall through to fallback
    }
  }
  return 'id-' + Math.random().toString(36).slice(2, 11) + '-' + Date.now().toString(36)
}
