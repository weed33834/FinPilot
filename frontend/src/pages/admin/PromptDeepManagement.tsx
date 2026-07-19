import { useCallback, useEffect, useState } from 'react'
import { listPrompts, type PromptTemplateItem } from '../../api/prompts.ts'
import {
  createABTest,
  createFewShot,
  createVersion,
  deleteFewShot,
  diffVersion,
  getABTestResults,
  listABTests,
  listFewShot,
  listVersions,
  reorderFewShot,
  rollbackVersion,
  startABTest,
  stopABTest,
  updateFewShot,
  type ABTestItem,
  type FewShotExample,
  type PromptVersionItem,
} from '../../api/promptDeep.ts'
import Modal from '../../components/ui/Modal.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'

type Tab = 'versions' | 'ab' | 'fewshot'

/* ------------------------------------------------------------------ */
/*  通用：diff 着色渲染                                                  */
/* ------------------------------------------------------------------ */

function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n')
  return (
    <pre className="admin-diff">
      {lines.map((ln, i) => {
        let cls = ''
        if (ln.startsWith('+++') || ln.startsWith('@@')) cls = 'diff-hunk'
        else if (ln.startsWith('+')) cls = 'diff-add'
        else if (ln.startsWith('-')) cls = 'diff-del'
        return (
          <span key={i} className={cls}>
            {ln || ' '}
            {'\n'}
          </span>
        )
      })}
    </pre>
  )
}

/* ------------------------------------------------------------------ */
/*  版本历史                                                            */
/* ------------------------------------------------------------------ */

function VersionsTab({ prompts }: { prompts: PromptTemplateItem[] }) {
  const [templateId, setTemplateId] = useState('')
  const [versions, setVersions] = useState<PromptVersionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [diff, setDiff] = useState<string | null>(null)
  const [diffVersionNum, setDiffVersionNum] = useState<number | null>(null)
  const [rolling, setRolling] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newContent, setNewContent] = useState('')
  const [newDesc, setNewDesc] = useState('')

  const load = useCallback(async () => {
    if (!templateId) return
    setLoading(true)
    setError(null)
    try {
      const res = await listVersions(templateId)
      setVersions(res.data.data ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    void load()
  }, [load])

  const handleDiff = async (v: number) => {
    setError(null)
    try {
      const res = await diffVersion(templateId, v)
      setDiff(res.data.data.diff || '（无差异）')
      setDiffVersionNum(v)
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取差异失败')
    }
  }

  const handleRollback = async () => {
    if (diffVersionNum == null) return
    if (!window.confirm(`确认回滚到版本 v${diffVersionNum}？当前内容将被覆盖。`)) return
    setRolling(true)
    try {
      await rollbackVersion(templateId, diffVersionNum)
      setDiff(null)
      setDiffVersionNum(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '回滚失败')
    } finally {
      setRolling(false)
    }
  }

  const handleCreate = async () => {
    if (!newContent.trim()) {
      setError('内容不能为空')
      return
    }
    try {
      await createVersion(templateId, { content: newContent, change_description: newDesc })
      setCreateOpen(false)
      setNewContent('')
      setNewDesc('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建版本失败')
    }
  }

  return (
    <div>
      <div className="admin-toolbar-left" style={{ marginBottom: 14 }}>
        <select
          className="admin-filter-select"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
        >
          <option value="">选择提示词模板</option>
          {prompts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary"
          onClick={() => setCreateOpen(true)}
          disabled={!templateId}
        >
          新建版本
        </button>
      </div>

      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}

      {!templateId ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>请先选择提示词模板</div>
      ) : loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>加载中…</div>
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 80 }}>版本</th>
                <th>变更说明</th>
                <th style={{ width: 90 }}>状态</th>
                <th style={{ width: 170 }}>创建时间</th>
                <th style={{ width: 120 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {versions.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                    暂无版本
                  </td>
                </tr>
              ) : (
                versions.map((v) => (
                  <tr key={v.id}>
                    <td className="admin-table-mono">v{v.version}</td>
                    <td>{v.change_description || '-'}</td>
                    <td>
                      {v.is_active ? (
                        <span className="badge success">当前</span>
                      ) : (
                        <span className="badge">历史</span>
                      )}
                    </td>
                    <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                      {v.created_at ? new Date(String(v.created_at)).toLocaleString() : '-'}
                    </td>
                    <td>
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleDiff(v.version)}
                      >
                        查看差异
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {diff !== null && diffVersionNum !== null && (
        <Modal
          title={`版本差异 — v${diffVersionNum} ↔ 当前`}
          onClose={() => {
            setDiff(null)
            setDiffVersionNum(null)
          }}
          footer={
            <>
              <button
                className="btn btn-danger"
                onClick={() => void handleRollback()}
                disabled={rolling}
              >
                {rolling ? '回滚中…' : '回滚到此版本'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setDiff(null)
                  setDiffVersionNum(null)
                }}
              >
                关闭
              </button>
            </>
          }
        >
          <DiffView diff={diff} />
        </Modal>
      )}

      {createOpen && (
        <Modal
          title="新建版本"
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleCreate()}>
                创建
              </button>
              <button className="btn btn-secondary" onClick={() => setCreateOpen(false)}>
                取消
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">变更说明</label>
            <input
              className="admin-form-input"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="简要描述本次变更"
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">版本内容</label>
            <textarea
              className="admin-form-textarea"
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              style={{ minHeight: 220, fontFamily: 'var(--font-mono, monospace)' }}
            />
          </div>
        </Modal>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  A/B 测试                                                            */
/* ------------------------------------------------------------------ */

const AB_STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  running: '运行中',
  completed: '已完成',
  stopped: '已停止',
}

function ABTestsTab({ prompts }: { prompts: PromptTemplateItem[] }) {
  const [tests, setTests] = useState<ABTestItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [results, setResults] = useState<Record<string, unknown> | null>(null)

  // create form
  const [name, setName] = useState('')
  const [promptKey, setPromptKey] = useState('')
  const [variantA, setVariantA] = useState('')
  const [variantB, setVariantB] = useState('')
  const [splitB, setSplitB] = useState(50)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listABTests({ page: 1, page_size: 100 })
      setTests(res.data.data.items ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleCreate = async () => {
    if (!name.trim() || !promptKey.trim() || !variantA || !variantB) {
      setError('请填写名称、prompt_key 并选择两个变体')
      return
    }
    if (variantA === variantB) {
      setError('变体 A 与变体 B 不能相同')
      return
    }
    try {
      await createABTest({
        name: name.trim(),
        prompt_key: promptKey.trim(),
        variant_a_id: variantA,
        variant_b_id: variantB,
        traffic_split_b: splitB,
      })
      setCreateOpen(false)
      setName('')
      setPromptKey('')
      setVariantA('')
      setVariantB('')
      setSplitB(50)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败')
    }
  }

  const handleToggle = async (t: ABTestItem) => {
    try {
      if (t.status === 'running') {
        await stopABTest(t.id)
      } else {
        await startABTest(t.id)
      }
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
    }
  }

  const handleResults = async (t: ABTestItem) => {
    try {
      const res = await getABTestResults(t.id)
      setResults(res.data.data ?? {})
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取结果失败')
    }
  }

  return (
    <div>
      <div className="admin-toolbar-left" style={{ marginBottom: 14, justifyContent: 'space-between' }}>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          新建 A/B 测试
        </button>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          刷新
        </button>
      </div>

      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>名称</th>
              <th style={{ width: 140 }}>prompt_key</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 90 }}>B 流量</th>
              <th style={{ width: 160 }}>创建时间</th>
              <th style={{ width: 170 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {tests.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  暂无 A/B 测试
                </td>
              </tr>
            ) : (
              tests.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>
                    {t.prompt_key}
                  </td>
                  <td>
                    <span className={`badge ${t.status === 'running' ? 'processing' : ''}`}>
                      {AB_STATUS_LABEL[t.status] || t.status}
                    </span>
                  </td>
                  <td>{t.traffic_split_b}%</td>
                  <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                    {t.created_at ? new Date(String(t.created_at)).toLocaleString() : '-'}
                  </td>
                  <td>
                    <div className="admin-actions">
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleToggle(t)}
                      >
                        {t.status === 'running' ? '停止' : '启动'}
                      </button>
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleResults(t)}
                      >
                        结果
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {createOpen && (
        <Modal
          title="新建 A/B 测试"
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleCreate()}>
                创建
              </button>
              <button className="btn btn-secondary" onClick={() => setCreateOpen(false)}>
                取消
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">测试名称</label>
            <input
              className="admin-form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">prompt_key</label>
            <input
              className="admin-form-input"
              value={promptKey}
              onChange={(e) => setPromptKey(e.target.value)}
              placeholder="如：report_summary"
              list="prompt-key-list"
            />
            <datalist id="prompt-key-list">
              {prompts.map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">变体 A（模板）</label>
            <select
              className="admin-form-select"
              value={variantA}
              onChange={(e) => setVariantA(e.target.value)}
            >
              <option value="">选择变体 A</option>
              {prompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">变体 B（模板）</label>
            <select
              className="admin-form-select"
              value={variantB}
              onChange={(e) => setVariantB(e.target.value)}
            >
              <option value="">选择变体 B</option>
              {prompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">变体 B 流量占比（%）— {splitB}</label>
            <input
              type="range"
              min={0}
              max={100}
              value={splitB}
              onChange={(e) => setSplitB(Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </div>
        </Modal>
      )}

      {results !== null && (
        <Modal title="A/B 测试结果" onClose={() => setResults(null)}>
          <ResultsView data={results} />
        </Modal>
      )}
    </div>
  )
}

function ResultsView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) {
    return <div style={{ color: '#9aa' }}>暂无结果数据</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {entries.map(([key, val]) => (
        <div key={key} className="admin-card" style={{ padding: 14 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>变体 {key}</div>
          {val && typeof val === 'object' ? (
            <table className="admin-table" style={{ fontSize: '0.78rem' }}>
              <tbody>
                {Object.entries(val as Record<string, unknown>).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ width: 200, color: '#9aa' }}>{k}</td>
                    <td>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div>{String(val)}</div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Few-shot 示例                                                       */
/* ------------------------------------------------------------------ */

function FewShotTab({ prompts }: { prompts: PromptTemplateItem[] }) {
  const [promptKey, setPromptKey] = useState('')
  const [examples, setExamples] = useState<FewShotExample[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<FewShotExample | null>(null)

  // form
  const [fInput, setFInput] = useState('')
  const [fOutput, setFOutput] = useState('')
  const [fCategory, setFCategory] = useState('')
  const [fQuality, setFQuality] = useState(5)
  const [fActive, setFActive] = useState(true)
  const [fOrder, setFOrder] = useState(0)

  const load = useCallback(async () => {
    if (!promptKey) {
      setExamples([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await listFewShot(promptKey)
      setExamples(res.data.data ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [promptKey])

  useEffect(() => {
    void load()
  }, [load])

  const openCreate = () => {
    setEditing(null)
    setFInput('')
    setFOutput('')
    setFCategory('')
    setFQuality(5)
    setFActive(true)
    setFOrder(examples.length)
    setEditOpen(true)
  }

  const openEdit = (ex: FewShotExample) => {
    setEditing(ex)
    setFInput(ex.input_text || '')
    setFOutput(ex.output_text || '')
    setFCategory(ex.category || '')
    setFQuality(ex.quality_score ?? 5)
    setFActive(ex.is_active ?? true)
    setFOrder(ex.display_order ?? 0)
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!fInput.trim() || !fOutput.trim()) {
      setError('输入和输出均不能为空')
      return
    }
    try {
      if (editing) {
        await updateFewShot(editing.id, {
          input_text: fInput,
          output_text: fOutput,
          category: fCategory,
          quality_score: fQuality,
          is_active: fActive,
          display_order: fOrder,
        })
      } else {
        await createFewShot({
          prompt_key: promptKey,
          input_text: fInput,
          output_text: fOutput,
          category: fCategory,
          quality_score: fQuality,
          is_active: fActive,
          display_order: fOrder,
        })
      }
      setEditOpen(false)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('确认删除该示例？')) return
    try {
      await deleteFewShot(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    }
  }

  const handleMove = async (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= examples.length) return
    const reordered = [...examples]
    ;[reordered[idx], reordered[target]] = [reordered[target], reordered[idx]]
    try {
      await reorderFewShot(promptKey, reordered.map((e) => e.id))
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '排序失败')
    }
  }

  return (
    <div>
      <div className="admin-toolbar-left" style={{ marginBottom: 14, justifyContent: 'space-between' }}>
        <input
          className="admin-search-input"
          value={promptKey}
          onChange={(e) => setPromptKey(e.target.value)}
          placeholder="输入 prompt_key 后回车加载…"
          list="fewshot-key-list"
          onKeyDown={(e) => {
            if (e.key === 'Enter') void load()
          }}
          style={{ minWidth: 260 }}
        />
        <datalist id="fewshot-key-list">
          {prompts.map((p) => (
            <option key={p.id} value={p.name} />
          ))}
        </datalist>
        <span style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-secondary" onClick={() => void load()} disabled={loading || !promptKey}>
            <ICONS.refresh size={14} />
            刷新
          </button>
          <button className="btn btn-primary" onClick={openCreate} disabled={!promptKey}>
            新建示例
          </button>
        </span>
      </div>

      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}

      {!promptKey ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>请输入 prompt_key</div>
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 60 }}>排序</th>
                <th>输入</th>
                <th>输出</th>
                <th style={{ width: 100 }}>分类</th>
                <th style={{ width: 70 }}>质量</th>
                <th style={{ width: 70 }}>启用</th>
                <th style={{ width: 150 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {examples.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                    {loading ? '加载中…' : '暂无示例'}
                  </td>
                </tr>
              ) : (
                examples.map((ex, idx) => (
                  <tr key={ex.id}>
                    <td>
                      <div className="admin-actions" style={{ flexDirection: 'column' }}>
                        <button
                          className="admin-action-btn"
                          style={{ padding: '0 6px' }}
                          onClick={() => void handleMove(idx, -1)}
                          disabled={idx === 0}
                        >
                          ↑
                        </button>
                        <button
                          className="admin-action-btn"
                          style={{ padding: '0 6px' }}
                          onClick={() => void handleMove(idx, 1)}
                          disabled={idx === examples.length - 1}
                        >
                          ↓
                        </button>
                      </div>
                    </td>
                    <td style={{ maxWidth: 260, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {ex.input_text}
                    </td>
                    <td style={{ maxWidth: 260, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {ex.output_text}
                    </td>
                    <td>{ex.category || '-'}</td>
                    <td>{ex.quality_score ?? '-'}</td>
                    <td>
                      {ex.is_active ? (
                        <span className="badge success">启用</span>
                      ) : (
                        <span className="badge">停用</span>
                      )}
                    </td>
                    <td>
                      <div className="admin-actions">
                        <button className="admin-action-btn" onClick={() => openEdit(ex)}>
                          编辑
                        </button>
                        <button
                          className="admin-action-btn"
                          onClick={() => void handleDelete(ex.id)}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {editOpen && (
        <Modal
          title={editing ? '编辑 Few-shot 示例' : '新建 Few-shot 示例'}
          onClose={() => setEditOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleSave()}>
                保存
              </button>
              <button className="btn btn-secondary" onClick={() => setEditOpen(false)}>
                取消
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">输入 (input)</label>
            <textarea
              className="admin-form-textarea"
              value={fInput}
              onChange={(e) => setFInput(e.target.value)}
              style={{ minHeight: 100 }}
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">输出 (output)</label>
            <textarea
              className="admin-form-textarea"
              value={fOutput}
              onChange={(e) => setFOutput(e.target.value)}
              style={{ minHeight: 100 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="admin-form-row" style={{ flex: 1 }}>
              <label className="admin-form-label">分类</label>
              <input
                className="admin-form-input"
                value={fCategory}
                onChange={(e) => setFCategory(e.target.value)}
              />
            </div>
            <div className="admin-form-row" style={{ flex: 1 }}>
              <label className="admin-form-label">质量分 (0-10)</label>
              <input
                type="number"
                className="admin-form-input"
                value={fQuality}
                min={0}
                max={10}
                onChange={(e) => setFQuality(Number(e.target.value))}
              />
            </div>
            <div className="admin-form-row" style={{ flex: 1 }}>
              <label className="admin-form-label">显示顺序</label>
              <input
                type="number"
                className="admin-form-input"
                value={fOrder}
                onChange={(e) => setFOrder(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label" style={{ flexDirection: 'row', display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={fActive}
                onChange={(e) => setFActive(e.target.checked)}
              />
              启用此示例
            </label>
          </div>
        </Modal>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  页面                                                                */
/* ------------------------------------------------------------------ */

export default function PromptDeepManagement() {
  const [tab, setTab] = useState<Tab>('versions')
  const [prompts, setPrompts] = useState<PromptTemplateItem[]>([])

  useEffect(() => {
    listPrompts({ page: 1, page_size: 200 })
      .then((res) => setPrompts(res.data.data.items ?? []))
      .catch(() => setPrompts([]))
  }, [])

  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">提示词进阶管理</h1>
        <p className="admin-page-desc">版本历史 / A/B 测试 / Few-shot 示例</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'versions' ? ' active' : ''}`}
          onClick={() => setTab('versions')}
        >
          版本历史
        </button>
        <button
          className={`tab-item${tab === 'ab' ? ' active' : ''}`}
          onClick={() => setTab('ab')}
        >
          A/B 测试
        </button>
        <button
          className={`tab-item${tab === 'fewshot' ? ' active' : ''}`}
          onClick={() => setTab('fewshot')}
        >
          Few-shot 示例
        </button>
      </div>

      {tab === 'versions' && <VersionsTab prompts={prompts} />}
      {tab === 'ab' && <ABTestsTab prompts={prompts} />}
      {tab === 'fewshot' && <FewShotTab prompts={prompts} />}
    </div>
  )
}
