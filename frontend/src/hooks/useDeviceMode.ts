import { useMediaQuery } from './useMediaQuery'

/** 移动端断点：<= 767px 视为移动设备（与 Tailwind md 断点对齐）。 */
export const MOBILE_QUERY = '(max-width: 767px)'

export interface DeviceMode {
  isMobile: boolean
  isDesktop: boolean
}

/** 设备模式判定：移动端走独立外壳/页面，桌面端走原 Sidebar 布局。 */
export function useDeviceMode(): DeviceMode {
  const isMobile = useMediaQuery(MOBILE_QUERY)
  return { isMobile, isDesktop: !isMobile }
}

export default useDeviceMode
