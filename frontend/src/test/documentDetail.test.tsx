import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders, seedAuth, mockMatchMedia } from './renderWithProviders'
import DocumentDetailMobile from '../pages/mobile/DocumentDetailMobile'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

// 延迟导入以使用 mock 后的 api
import { api } from '../api/client'

beforeEach(() => {
  seedAuth()
  mockMatchMedia(true)
  vi.clearAllMocks()
})

describe('DocumentDetailMobile', () => {
  it('加载后渲染文档字段', async () => {
    const doc = {
      id: '1',
      filename: 'statement.pdf',
      status: 'success',
      confidence: 0.95,
      parse_result: { amount: 100 },
      error_message: null,
      created_at: '2024-01-01T00:00:00Z',
    }
    ;(api.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { data: doc } })

    renderWithProviders(<DocumentDetailMobile id="1" />, { route: '/documents/1' })

    expect(await screen.findByText('statement.pdf')).toBeInTheDocument()
    expect(await screen.findByText('95%')).toBeInTheDocument()
    // 返回按钮已移除（页头 MobilePageHeader 的返回箭头负责导航）
  })

  it('加载失败时展示错误信息', async () => {
    ;(api.get as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'))

    renderWithProviders(<DocumentDetailMobile id="1" />, { route: '/documents/1' })

    await waitFor(() => {
      const alert = document.querySelector('.mdetail__error')
      expect(alert).toBeInTheDocument()
    })
  })
})
