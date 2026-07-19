interface LoadingProps {
  text?: string
}

// 行内小加载，用于按钮、局部刷新
export default function Loading({ text = '加载中' }: LoadingProps) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{text}</span>
    </div>
  )
}

// 卡片骨架，匹配 Dashboard 等多卡片页
export function PageSkeleton() {
  return (
    <div role="status" aria-live="polite" aria-label="加载中">
      <div className="skeleton-stat-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-stat" />
        ))}
      </div>
      <div className="skeleton skeleton-block" />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
        <div className="skeleton skeleton-block" style={{ height: 180 }} />
        <div className="skeleton skeleton-block" style={{ height: 180 }} />
      </div>
    </div>
  )
}
