import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // 独立缓存目录：与 Vite 开发服务器(node_modules/.vite)隔离，避免两者同时运行时
  // dep 优化产物被开发服务器进程锁住，导致 vitest 的 dep optimizer 卡死（Permission denied / 无限等待）。
  cacheDir: 'node_modules/.vitest-cache',
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
