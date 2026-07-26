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
      <div className="skeleton skeleton-block" style={{ height: 180 }} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
        <div className="skeleton skeleton-block" style={{ height: 180 }} />
        <div className="skeleton skeleton-block" style={{ height: 180 }} />
      </div>
    </div>
  )
}

// 表格行骨架
interface TableSkeletonProps {
  rows?: number
  cols?: number
}

export function TableSkeleton({ rows = 5, cols = 4 }: TableSkeletonProps) {
  return (
    <div className="table-wrapper" role="status" aria-live="polite" aria-label="加载中">
      <table>
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}>
                <div className="skeleton skeleton-th" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}>
                  <div className="skeleton skeleton-td" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// 列表骨架
interface ListSkeletonProps {
  items?: number
}

export function ListSkeleton({ items = 6 }: ListSkeletonProps) {
  return (
    <div role="status" aria-live="polite" aria-label="加载中">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="card" style={{ padding: 'var(--space-3)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            <div className="skeleton" style={{ width: 40, height: 40, borderRadius: 'var(--radius-sm)' }} />
            <div style={{ flex: 1 }}>
              <div className="skeleton" style={{ width: '40%', height: 14, marginBottom: 6 }} />
              <div className="skeleton" style={{ width: '70%', height: 12 }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// 详情页骨架
export function DetailSkeleton() {
  return (
    <div role="status" aria-live="polite" aria-label="加载中">
      <div className="skeleton" style={{ width: '30%', height: 28, marginBottom: 'var(--space-4)' }} />
      <div className="card" style={{ padding: 'var(--space-4)' }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-3)' }}>
            <div className="skeleton" style={{ width: 100, height: 14 }} />
            <div className="skeleton" style={{ flex: 1, height: 14 }} />
          </div>
        ))}
      </div>
    </div>
  )
}
