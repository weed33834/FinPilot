import * as Sentry from '@sentry/react'

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN || ''
const SENTRY_ENVIRONMENT = import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE
const SENTRY_TRACES_SAMPLE_RATE = Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || 0.1)

let initialized = false

export function setupSentry(): void {
  if (!SENTRY_DSN || initialized) return
  initialized = true

  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENVIRONMENT,
    release: import.meta.env.VITE_APP_VERSION,
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true }),
    ],
    tracesSampleRate: SENTRY_TRACES_SAMPLE_RATE,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    beforeSend(event) {
      // 过滤敏感信息
      if (event.request?.headers) {
        const headers = event.request.headers
        for (const key of Object.keys(headers)) {
          if (key.toLowerCase() === 'authorization' || key.toLowerCase() === 'cookie') {
            headers[key] = '[REDACTED]'
          }
        }
      }
      return event
    },
  })
}

export function captureException(error: unknown, context?: Record<string, unknown>): void {
  if (!initialized) return
  Sentry.captureException(error, { extra: context })
}

export function setUserContext(user: { id: string; username?: string; role?: string }): void {
  if (!initialized) return
  Sentry.setUser(user)
}

export function clearUserContext(): void {
  if (!initialized) return
  Sentry.setUser(null)
}

export const SentryErrorBoundary = Sentry.ErrorBoundary
