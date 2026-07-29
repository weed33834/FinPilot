import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useDeviceMode } from '../hooks/useDeviceMode'
import { mockMatchMedia } from './renderWithProviders'

describe('useMediaQuery', () => {
  beforeEach(() => mockMatchMedia(false))

  it('返回 matchMedia 的匹配结果', () => {
    mockMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(true)

    mockMatchMedia(false)
    const { result: r2 } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(r2.current).toBe(false)
  })
})

describe('useDeviceMode', () => {
  beforeEach(() => mockMatchMedia(false))

  it('断点内判定为移动端', () => {
    mockMatchMedia(true)
    const { result } = renderHook(() => useDeviceMode())
    expect(result.current.isMobile).toBe(true)
    expect(result.current.isDesktop).toBe(false)
  })

  it('断点外判定为桌面端', () => {
    mockMatchMedia(false)
    const { result } = renderHook(() => useDeviceMode())
    expect(result.current.isMobile).toBe(false)
    expect(result.current.isDesktop).toBe(true)
  })
})
