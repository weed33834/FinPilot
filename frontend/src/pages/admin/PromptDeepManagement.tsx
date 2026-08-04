import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
import EmptyState from '../../components/ui/EmptyState.tsx'
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
  const { t } = useTranslation('adminPromptDeep')
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
      setError(e instanceof Error ? e.message : t('errors.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [templateId, t])

  useEffect(() => {
    void load()
  }, [load])

  const handleDiff = async (v: number) => {
    setError(null)
    try {
      const res = await diffVersion(templateId, v)
      setDiff(res.data.data.diff || t('versions.noDiff'))
      setDiffVersionNum(v)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('versions.diffFailed'))
    }
  }

  const handleRollback = async () => {
    if (diffVersionNum == null) return
    if (!window.confirm(t('versions.rollbackConfirm', { version: diffVersionNum }))) return
    setRolling(true)
    try {
      await rollbackVersion(templateId, diffVersionNum)
      setDiff(null)
      setDiffVersionNum(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('versions.rollbackFailed'))
    } finally {
      setRolling(false)
    }
  }

  const handleCreate = async () => {
    if (!newContent.trim()) {
      setError(t('versions.contentRequired'))
      return
    }
    try {
      await createVersion(templateId, { content: newContent, change_description: newDesc })
      setCreateOpen(false)
      setNewContent('')
      setNewDesc('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('versions.createFailed'))
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
          <option value="">{t('versions.selectTemplate')}</option>
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
          {t('versions.createVersion')}
        </button>
      </div>

      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()}>
            {t('actions.retry')}
          </button>
        </div>
      )}

      {!templateId ? (
        <EmptyState
          icon="templates"
          title={t('versions.pleaseSelectTemplate')}
          description={t('versions.pleaseSelectTemplateDesc')}
        />
      ) : loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>{t('actions.loading')}</div>
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 80 }}>{t('versions.colVersion')}</th>
                <th>{t('versions.colChangeDesc')}</th>
                <th style={{ width: 90 }}>{t('table.status')}</th>
                <th style={{ width: 170 }}>{t('table.createdAt')}</th>
                <th style={{ width: 120 }}>{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {versions.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                    {t('versions.empty')}
                  </td>
                </tr>
              ) : (
                versions.map((v) => (
                  <tr key={v.id}>
                    <td className="admin-table-mono">v{v.version}</td>
                    <td>{v.change_description || '-'}</td>
                    <td>
                      {v.is_active ? (
                        <span className="badge success">{t('versions.badgeCurrent')}</span>
                      ) : (
                        <span className="badge">{t('versions.badgeHistory')}</span>
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
                        {t('versions.viewDiff')}
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
          title={t('versions.diffTitle', { version: diffVersionNum })}
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
                {rolling ? t('versions.rolling') : t('versions.rollback')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setDiff(null)
                  setDiffVersionNum(null)
                }}
              >
                {t('actions.close')}
              </button>
            </>
          }
        >
          <DiffView diff={diff} />
        </Modal>
      )}

      {createOpen && (
        <Modal
          title={t('versions.createModalTitle')}
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleCreate()}>
                {t('actions.create')}
              </button>
              <button className="btn btn-secondary" onClick={() => setCreateOpen(false)}>
                {t('actions.cancel')}
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">{t('versions.fieldChangeDesc')}</label>
            <input
              className="admin-form-input"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder={t('versions.fieldChangeDescPlaceholder')}
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('versions.fieldContent')}</label>
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

function ABTestsTab({ prompts }: { prompts: PromptTemplateItem[] }) {
  const { t } = useTranslation('adminPromptDeep')
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
      setError(e instanceof Error ? e.message : t('errors.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const handleCreate = async () => {
    if (!name.trim() || !promptKey.trim() || !variantA || !variantB) {
      setError(t('ab.validationFill'))
      return
    }
    if (variantA === variantB) {
      setError(t('ab.validationSameVariant'))
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
      setError(e instanceof Error ? e.message : t('ab.createFailed'))
    }
  }

  const handleToggle = async (tst: ABTestItem) => {
    try {
      if (tst.status === 'running') {
        await stopABTest(tst.id)
      } else {
        await startABTest(tst.id)
      }
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('ab.toggleFailed'))
    }
  }

  const handleResults = async (tst: ABTestItem) => {
    try {
      const res = await getABTestResults(tst.id)
      setResults(res.data.data ?? {})
    } catch (e) {
      setError(e instanceof Error ? e.message : t('ab.resultsFailed'))
    }
  }

  const statusLabel = (status: string) =>
    t(`ab.status.${status}`, { defaultValue: status })

  return (
    <div>
      <div className="admin-toolbar-left" style={{ marginBottom: 14, justifyContent: 'space-between' }}>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          {t('ab.create')}
        </button>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          {t('actions.refresh')}
        </button>
      </div>

      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()}>
            {t('actions.retry')}
          </button>
        </div>
      )}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t('ab.colName')}</th>
              <th style={{ width: 140 }}>{t('ab.colPromptKey')}</th>
              <th style={{ width: 90 }}>{t('table.status')}</th>
              <th style={{ width: 90 }}>{t('ab.colTrafficB')}</th>
              <th style={{ width: 160 }}>{t('table.createdAt')}</th>
              <th style={{ width: 170 }}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {tests.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  {t('ab.empty')}
                </td>
              </tr>
            ) : (
              tests.map((tst) => (
                <tr key={tst.id}>
                  <td>{tst.name}</td>
                  <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>
                    {tst.prompt_key}
                  </td>
                  <td>
                    <span className={`badge ${tst.status === 'running' ? 'processing' : ''}`}>
                      {statusLabel(tst.status)}
                    </span>
                  </td>
                  <td>{tst.traffic_split_b}%</td>
                  <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                    {tst.created_at ? new Date(String(tst.created_at)).toLocaleString() : '-'}
                  </td>
                  <td>
                    <div className="admin-actions">
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleToggle(tst)}
                      >
                        {tst.status === 'running' ? t('ab.actionStop') : t('ab.actionStart')}
                      </button>
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleResults(tst)}
                      >
                        {t('ab.actionResults')}
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
          title={t('ab.createModalTitle')}
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleCreate()}>
                {t('actions.create')}
              </button>
              <button className="btn btn-secondary" onClick={() => setCreateOpen(false)}>
                {t('actions.cancel')}
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">{t('ab.fieldName')}</label>
            <input
              className="admin-form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('ab.fieldPromptKey')}</label>
            <input
              className="admin-form-input"
              value={promptKey}
              onChange={(e) => setPromptKey(e.target.value)}
              placeholder={t('ab.fieldPromptKeyPlaceholder')}
              list="prompt-key-list"
            />
            <datalist id="prompt-key-list">
              {prompts.map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('ab.fieldVariantA')}</label>
            <select
              className="admin-form-select"
              value={variantA}
              onChange={(e) => setVariantA(e.target.value)}
            >
              <option value="">{t('ab.selectVariantA')}</option>
              {prompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('ab.fieldVariantB')}</label>
            <select
              className="admin-form-select"
              value={variantB}
              onChange={(e) => setVariantB(e.target.value)}
            >
              <option value="">{t('ab.selectVariantB')}</option>
              {prompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('ab.fieldTrafficB', { value: splitB })}</label>
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
        <Modal title={t('ab.resultsModalTitle')} onClose={() => setResults(null)}>
          <ResultsView data={results} />
        </Modal>
      )}
    </div>
  )
}

function ResultsView({ data }: { data: Record<string, unknown> }) {
  const { t } = useTranslation('adminPromptDeep')
  const entries = Object.entries(data)
  if (entries.length === 0) {
    return <div style={{ color: '#9aa' }}>{t('ab.resultsEmpty')}</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {entries.map(([key, val]) => (
        <div key={key} className="admin-card" style={{ padding: 14 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>{t('ab.resultsVariant', { key })}</div>
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
  const { t } = useTranslation('adminPromptDeep')
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
      setError(e instanceof Error ? e.message : t('errors.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [promptKey, t])

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
      setError(t('fewshot.validationRequired'))
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
      setError(e instanceof Error ? e.message : t('fewshot.saveFailed'))
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm(t('fewshot.deleteConfirm'))) return
    try {
      await deleteFewShot(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('fewshot.deleteFailed'))
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
      setError(e instanceof Error ? e.message : t('fewshot.reorderFailed'))
    }
  }

  return (
    <div>
      <div className="admin-toolbar-left" style={{ marginBottom: 14, justifyContent: 'space-between' }}>
        <input
          className="admin-search-input"
          value={promptKey}
          onChange={(e) => setPromptKey(e.target.value)}
          placeholder={t('fewshot.searchPlaceholder')}
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
            {t('actions.refresh')}
          </button>
          <button className="btn btn-primary" onClick={openCreate} disabled={!promptKey}>
            {t('fewshot.create')}
          </button>
        </span>
      </div>

      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()}>
            {t('actions.retry')}
          </button>
        </div>
      )}

      {!promptKey ? (
        <EmptyState
          icon="search"
          title={t('fewshot.pleaseInputKey')}
          description={t('fewshot.pleaseInputKeyDesc')}
        />
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 60 }}>{t('fewshot.colOrder')}</th>
                <th>{t('fewshot.colInput')}</th>
                <th>{t('fewshot.colOutput')}</th>
                <th style={{ width: 100 }}>{t('fewshot.colCategory')}</th>
                <th style={{ width: 70 }}>{t('fewshot.colQuality')}</th>
                <th style={{ width: 70 }}>{t('fewshot.colActive')}</th>
                <th style={{ width: 150 }}>{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {examples.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                    {loading ? t('actions.loading') : t('fewshot.empty')}
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
                        <span className="badge success">{t('fewshot.badgeActive')}</span>
                      ) : (
                        <span className="badge">{t('fewshot.badgeInactive')}</span>
                      )}
                    </td>
                    <td>
                      <div className="admin-actions">
                        <button className="admin-action-btn" onClick={() => openEdit(ex)}>
                          {t('actions.edit')}
                        </button>
                        <button
                          className="admin-action-btn"
                          onClick={() => void handleDelete(ex.id)}
                        >
                          {t('actions.delete')}
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
          title={editing ? t('fewshot.editModalTitle') : t('fewshot.createModalTitle')}
          onClose={() => setEditOpen(false)}
          footer={
            <>
              <button className="btn btn-primary" onClick={() => void handleSave()}>
                {t('actions.save')}
              </button>
              <button className="btn btn-secondary" onClick={() => setEditOpen(false)}>
                {t('actions.cancel')}
              </button>
            </>
          }
        >
          <div className="admin-form-row">
            <label className="admin-form-label">{t('fewshot.fieldInput')}</label>
            <textarea
              className="admin-form-textarea"
              value={fInput}
              onChange={(e) => setFInput(e.target.value)}
              style={{ minHeight: 100 }}
            />
          </div>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('fewshot.fieldOutput')}</label>
            <textarea
              className="admin-form-textarea"
              value={fOutput}
              onChange={(e) => setFOutput(e.target.value)}
              style={{ minHeight: 100 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="admin-form-row" style={{ flex: 1 }}>
              <label className="admin-form-label">{t('fewshot.fieldCategory')}</label>
              <input
                className="admin-form-input"
                value={fCategory}
                onChange={(e) => setFCategory(e.target.value)}
              />
            </div>
            <div className="admin-form-row" style={{ flex: 1 }}>
              <label className="admin-form-label">{t('fewshot.fieldQuality')}</label>
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
              <label className="admin-form-label">{t('fewshot.fieldOrder')}</label>
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
              {t('fewshot.fieldActive')}
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
  const { t } = useTranslation('adminPromptDeep')
  const [tab, setTab] = useState<Tab>('versions')
  const [prompts, setPrompts] = useState<PromptTemplateItem[]>([])

  useEffect(() => {
    listPrompts({ page: 1, page_size: 100 })
      .then((res) => setPrompts(res.data.data.items ?? []))
      .catch(() => setPrompts([]))
  }, [])

  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('subtitle')}</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'versions' ? ' active' : ''}`}
          onClick={() => setTab('versions')}
        >
          {t('tabs.versions')}
        </button>
        <button
          className={`tab-item${tab === 'ab' ? ' active' : ''}`}
          onClick={() => setTab('ab')}
        >
          {t('tabs.ab')}
        </button>
        <button
          className={`tab-item${tab === 'fewshot' ? ' active' : ''}`}
          onClick={() => setTab('fewshot')}
        >
          {t('tabs.fewshot')}
        </button>
      </div>

      {tab === 'versions' && <VersionsTab prompts={prompts} />}
      {tab === 'ab' && <ABTestsTab prompts={prompts} />}
      {tab === 'fewshot' && <FewShotTab prompts={prompts} />}
    </div>
  )
}
