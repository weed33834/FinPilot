import { createContext, useContext, type ReactNode } from 'react'
import { useDeviceMode, type DeviceMode } from '../hooks/useDeviceMode'

const DeviceContext = createContext<DeviceMode | null>(null)

/**
 * 设备模式 Provider：在应用根部包一层，所有页面/外壳统一读取同一份 isMobile，
 * 避免多处各自监听 matchMedia 造成重复渲染与状态不一致。
 */
export function DeviceProvider({ children }: { children: ReactNode }) {
  const mode = useDeviceMode()
  return <DeviceContext.Provider value={mode}>{children}</DeviceContext.Provider>
}

/**
 * 读取设备模式。未包裹 Provider 时兜底为桌面端，保证组件可独立渲染（如单测）。
 */
export function useDevice(): DeviceMode {
  const ctx = useContext(DeviceContext)
  if (!ctx) return { isMobile: false, isDesktop: true }
  return ctx
}

export default DeviceContext
