import type { WebSocketStatus } from '../hooks/useWebSocket.ts'

/**
 * RealtimeIndicator
 * -----------------
 * 实时连接状态指示灯，放置于管理后台顶栏。
 *  - 绿色：已连接
 *  - 黄色（脉冲）：连接中 / 重连中
 *  - 红色：已断开 / 错误
 */

interface RealtimeIndicatorProps {
  status: WebSocketStatus
  /** 自定义类名 */
  className?: string
}

const STATUS_META: Record<
  WebSocketStatus,
  { color: string; label: string; pulse: boolean }
> = {
  connected: { color: '#22c55e', label: '实时连接正常', pulse: false },
  connecting: { color: '#eab308', label: '正在连接实时服务…', pulse: true },
  disconnected: { color: '#ef4444', label: '实时连接已断开', pulse: false },
  error: { color: '#ef4444', label: '实时连接异常', pulse: false },
}

export default function RealtimeIndicator({ status, className }: RealtimeIndicatorProps) {
  const meta = STATUS_META[status] || STATUS_META.disconnected
  return (
    <span
      className={`realtime-indicator${className ? ` ${className}` : ''}`}
      title={meta.label}
      role="status"
      aria-label={meta.label}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: meta.color,
          boxShadow: `0 0 6px ${meta.color}`,
          display: 'inline-block',
          animation: meta.pulse ? 'rt-pulse 1.2s ease-in-out infinite' : 'none',
        }}
      />
      <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted, #9aa)' }}>
        实时
      </span>
      <style>{`
        @keyframes rt-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </span>
  )
}
