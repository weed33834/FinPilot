import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { setupSentry } from './observability.ts'
import './index.css'
import './i18n/config.ts'

setupSentry()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // 30s 内不重新请求
      retry: 1,                // 失败重试 1 次
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element #root not found')
ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
