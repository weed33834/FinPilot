import { useMemo, useState } from 'react'
import EmptyState from '../ui/EmptyState.tsx'
import { CHART_COLORS } from './chartTokens.ts'

export interface Chart3DPoint {
  x: number
  y: number
  z: number
  label?: string
  color?: string
}

interface Chart3DProps {
  data: Chart3DPoint[]
  width?: number
  height?: number
}

const COS30 = Math.cos(Math.PI / 6) // ≈ 0.8660
const SIN30 = Math.sin(Math.PI / 6) // 0.5
const GRID_DIVS = 4
const PADDING = 56

// 按规格的等距投影：
//   screenX = (x - z) * cos(30°)
//   screenY = y + (x + z) * sin(30°)
function project(x: number, y: number, z: number) {
  return {
    px: (x - z) * COS30,
    py: y + (x + z) * SIN30,
  }
}

interface ProjPoint {
  px: number
  py: number
}

interface SvgPoint {
  x: number
  y: number
}

interface GridLine {
  from: SvgPoint
  to: SvgPoint
  plane: 'xz' | 'xy' | 'yz'
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

export default function Chart3D({ data, width = 640, height = 480 }: Chart3DProps) {
  const [hovered, setHovered] = useState<number | null>(null)

  const model = useMemo(() => {
    if (data.length === 0) return null

    let xMin = Infinity
    let xMax = -Infinity
    let yMin = Infinity
    let yMax = -Infinity
    let zMin = Infinity
    let zMax = -Infinity
    for (const p of data) {
      if (p.x < xMin) xMin = p.x
      if (p.x > xMax) xMax = p.x
      if (p.y < yMin) yMin = p.y
      if (p.y > yMax) yMax = p.y
      if (p.z < zMin) zMin = p.z
      if (p.z > zMax) zMax = p.z
    }

    // 给各轴留出少量边距，避免点贴边
    const padAxis = (a: number, b: number) => {
      const span = Math.abs(b - a) || Math.max(Math.abs(a), Math.abs(b), 1)
      const m = span * 0.08
      return [a - m, b + m] as const
    }
    ;[xMin, xMax] = padAxis(xMin, xMax)
    ;[yMin, yMax] = padAxis(yMin, yMax)
    ;[zMin, zMax] = padAxis(zMin, zMax)

    // 8 个包围盒角点（用于计算投影包围盒，缩放适配画布）
    const corners3d: Array<[number, number, number]> = [
      [xMin, yMin, zMin],
      [xMax, yMin, zMin],
      [xMin, yMax, zMin],
      [xMax, yMax, zMin],
      [xMin, yMin, zMax],
      [xMax, yMin, zMax],
      [xMin, yMax, zMax],
      [xMax, yMax, zMax],
    ]

    const projCorners = corners3d.map(([x, y, z]) => project(x, y, z))
    let minPx = Infinity
    let maxPx = -Infinity
    let minPy = Infinity
    let maxPy = -Infinity
    for (const c of projCorners) {
      if (c.px < minPx) minPx = c.px
      if (c.px > maxPx) maxPx = c.px
      if (c.py < minPy) minPy = c.py
      if (c.py > maxPy) maxPy = c.py
    }
    const rangePx = maxPx - minPx || 1
    const rangePy = maxPy - minPy || 1

    const plotW = width - PADDING * 2
    const plotH = height - PADDING * 2
    const scale = Math.min(plotW / rangePx, plotH / rangePy)

    // 将投影坐标转换为 SVG 坐标（sy 直接作为屏幕 y，向下为正）
    const toSvg = (p: ProjPoint) => ({
      x: PADDING + (p.px - minPx) * scale + (plotW - rangePx * scale) / 2,
      y: PADDING + (p.py - minPy) * scale + (plotH - rangePy * scale) / 2,
    })

    // 网格线：三个轴平面各画 GRID_DIVS 条平行线
    const gridLines: GridLine[] = []
    // X-Z 平面 (y = yMin)
    for (let i = 0; i <= GRID_DIVS; i++) {
      const t = i / GRID_DIVS
      const z = lerp(zMin, zMax, t)
      gridLines.push({
        from: toSvg(project(xMin, yMin, z)),
        to: toSvg(project(xMax, yMin, z)),
        plane: 'xz',
      })
      const x = lerp(xMin, xMax, t)
      gridLines.push({
        from: toSvg(project(x, yMin, zMin)),
        to: toSvg(project(x, yMin, zMax)),
        plane: 'xz',
      })
    }
    // X-Y 平面 (z = zMin)
    for (let i = 0; i <= GRID_DIVS; i++) {
      const t = i / GRID_DIVS
      const y = lerp(yMin, yMax, t)
      gridLines.push({
        from: toSvg(project(xMin, y, zMin)),
        to: toSvg(project(xMax, y, zMin)),
        plane: 'xy',
      })
      const x = lerp(xMin, xMax, t)
      gridLines.push({
        from: toSvg(project(x, yMin, zMin)),
        to: toSvg(project(x, yMax, zMin)),
        plane: 'xy',
      })
    }
    // Y-Z 平面 (x = xMin)
    for (let i = 0; i <= GRID_DIVS; i++) {
      const t = i / GRID_DIVS
      const z = lerp(zMin, zMax, t)
      gridLines.push({
        from: toSvg(project(xMin, yMin, z)),
        to: toSvg(project(xMin, yMax, z)),
        plane: 'yz',
      })
      const y = lerp(yMin, yMax, t)
      gridLines.push({
        from: toSvg(project(xMin, y, zMin)),
        to: toSvg(project(xMin, y, zMax)),
        plane: 'yz',
      })
    }

    // 三条主轴（从原点 (xMin, yMin, zMin) 出发）
    const origin = toSvg(project(xMin, yMin, zMin))
    const axes = [
      {
        label: 'X',
        end: toSvg(project(xMax, yMin, zMin)),
      },
      {
        label: 'Y',
        end: toSvg(project(xMin, yMax, zMin)),
      },
      {
        label: 'Z',
        end: toSvg(project(xMin, yMin, zMax)),
      },
    ]

    // 数据点
    const points = data.map((p, idx) => {
      const sp = toSvg(project(p.x, p.y, p.z))
      return {
        ...p,
        sx: sp.x,
        sy: sp.y,
        color: p.color || CHART_COLORS[idx % CHART_COLORS.length],
        idx,
      }
    })

    return { gridLines, axes, origin, points, ranges: { xMin, xMax, yMin, yMax, zMin, zMax } }
  }, [data, width, height])

  if (!model) {
    return (
      <div className="chart-container chart-container-lg">
        <EmptyState title="暂无 3D 数据" description="请提供数据点以渲染三维散点图。" icon="queries" />
      </div>
    )
  }

  const planeStroke: Record<GridLine['plane'], string> = {
    xz: 'var(--color-border-light)',
    xy: 'var(--color-border-light)',
    yz: 'var(--color-border-light)',
  }

  const hoveredPoint = hovered !== null ? model.points[hovered] : null

  return (
    <div className="chart-container chart-container-lg" style={{ position: 'relative' }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="三维散点图"
      >
        {/* 网格平面 */}
        <g>
          {model.gridLines.map((line, i) => (
            <line
              key={`grid-${i}`}
              x1={line.from.x}
              y1={line.from.y}
              x2={line.to.x}
              y2={line.to.y}
              stroke={planeStroke[line.plane]}
              strokeWidth={1}
              strokeDasharray="2 3"
              opacity={0.7}
            />
          ))}
        </g>

        {/* 主轴 */}
        <g>
          {model.axes.map((ax) => (
            <g key={ax.label}>
              <line
                x1={model.origin.x}
                y1={model.origin.y}
                x2={ax.end.x}
                y2={ax.end.y}
                stroke="var(--color-text-muted)"
                strokeWidth={1.5}
              />
              <text
                x={ax.end.x + 12}
                y={ax.end.y}
                fontSize={13}
                fontWeight={700}
                fill="var(--color-text)"
                dominantBaseline="middle"
              >
                {ax.label}
              </text>
            </g>
          ))}
        </g>

        {/* 数据点 */}
        <g>
          {model.points.map((p) => (
            <circle
              key={`pt-${p.idx}`}
              cx={p.sx}
              cy={p.sy}
              r={hovered === p.idx ? 7 : 4.5}
              fill={p.color}
              stroke="#fff"
              strokeWidth={1.5}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHovered(p.idx)}
              onMouseLeave={() => setHovered(null)}
            >
              <title>
                {p.label ? `${p.label}\n` : ''}x: {p.x.toFixed(2)}, y: {p.y.toFixed(2)}, z:{' '}
                {p.z.toFixed(2)}
              </title>
            </circle>
          ))}
        </g>

        {/* 悬浮提示框 */}
        {hoveredPoint && (
          <g pointerEvents="none">
            {(() => {
              const lines = [
                hoveredPoint.label ? hoveredPoint.label : `点 ${hoveredPoint.idx + 1}`,
                `X: ${hoveredPoint.x.toFixed(2)}`,
                `Y: ${hoveredPoint.y.toFixed(2)}`,
                `Z: ${hoveredPoint.z.toFixed(2)}`,
              ]
              const boxW = 132
              const boxH = lines.length * 16 + 10
              let bx = hoveredPoint.sx + 12
              let by = hoveredPoint.sy - boxH - 8
              if (bx + boxW > width) bx = hoveredPoint.sx - boxW - 12
              if (by < 4) by = hoveredPoint.sy + 12
              return (
                <>
                  <rect
                    x={bx}
                    y={by}
                    width={boxW}
                    height={boxH}
                    rx={6}
                    fill="var(--color-surface)"
                    stroke="var(--color-border)"
                  />
                  {lines.map((ln, i) => (
                    <text
                      key={i}
                      x={bx + 10}
                      y={by + 16 + i * 16}
                      fontSize={11}
                      fill={i === 0 ? 'var(--color-text)' : 'var(--color-text-secondary)'}
                      fontWeight={i === 0 ? 700 : 400}
                    >
                      {ln}
                    </text>
                  ))}
                </>
              )
            })()}
          </g>
        )}
      </svg>
    </div>
  )
}
