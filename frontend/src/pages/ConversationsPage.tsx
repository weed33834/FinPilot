import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { toast } from '../components/ui/Toaster'
import { confirm } from '../components/ui/ConfirmDialog'
import { ICONS } from '../components/ui/Icons'
import Modal from '../components/ui/Modal'
import Loading from '../components/ui/Loading'
import EmptyState from '../components/ui/EmptyState'
import MarkdownRenderer from '../components/MarkdownRenderer'
import { formatDateTime } from '../utils/format'
import { getErrorMessage } from '../utils/errors'
import type { DataResponse, PaginatedResponse } from '../types/report'

// ==================== 类型定义 ====================

interface Conversation {
  id: string
  title: string
  is_archived: boolean
  message_count: number
  created_at: string
  updated_at: string
}

interface ConversationMessage {
  role: string
  content: string
  timestamp: string
}

interface ConversationDetail extends Conversation {
  messages: ConversationMessage[]
}

// ==================== 工具函数 ====================

/** 从导出接口返回体中提取 Markdown 文本，兼容纯字符串 / { content } / { markdown } 等形态。 */
function extractMarkdown(payload: unknown): string {
  if (typeof payload === 'string') return payload
  const envelope = payload as { data?: unknown } | undefined
  const data = envelope?.data
  if (typeof data === 'string') return data
  if (data && typeof data === 'object') {
    const obj = data as { content?: unknown; markdown?: unknown }
    if (typeof obj.content === 'string') return obj.content
    if (typeof obj.markdown === 'string') return obj.markdown
  }
  return JSON.stringify(payload, null, 2)
}

/** 将对话标题转换为安全的文件名。 */
function toFileName(title: string): string {
  const safe = title
    .replace(/[\\/:*?"<>|\n\r\t]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 80)
  return safe || 'conversation'
}

/** 触发浏览器下载文本文件。 */
function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// ==================== 页面组件 ====================

export default function ConversationsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [archived, setArchived] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [exportingId, setExportingId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  // 当前正在执行 归档/取消归档/删除 的对话 id，用于禁用对应行按钮
  const [actingId, setActingId] = useState<string | null>(null)

  // 搜索防抖：输入停止 350ms 后触发后端检索（按标题 + 消息内容匹配）
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQ(searchTerm.trim()), 350)
    return () => clearTimeout(handle)
  }, [searchTerm])

  // ---- 对话列表（按 archived 分桶，后端搜索 + 无限滚动加载更多）----
  const {
    data,
    isLoading,
    error,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
  } = useInfiniteQuery({
    queryKey: ['conversations', archived, debouncedQ],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = {
        archived,
        page: pageParam,
        page_size: 20,
      }
      if (debouncedQ) params.q = debouncedQ
      const response = await api.get<DataResponse<PaginatedResponse<Conversation>>>(
        '/conversations',
        { params },
      )
      return (
        response.data.data ?? {
          total: 0,
          page: pageParam,
          page_size: 20,
          items: [],
        }
      )
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page * lastPage.page_size < lastPage.total
        ? lastPage.page + 1
        : undefined,
  })

  const conversations = data?.pages.flatMap((p) => p.items) ?? []
  const total = data?.pages[0]?.total ?? 0

  // ---- 对话详情（打开 Modal 时按需拉取）----
  const { data: detail, isLoading: detailLoading } = useQuery<ConversationDetail | null>({
    queryKey: ['conversation-detail', selectedId],
    queryFn: async () => {
      const response = await api.get<DataResponse<ConversationDetail>>(
        `/conversations/${selectedId}`,
      )
      return response.data.data ?? null
    },
    enabled: !!selectedId,
  })

  // ---- 更新（归档 / 取消归档）----
  const updateMutation = useMutation({
    mutationFn: async (vars: { id: string; is_archived: boolean }) => {
      await api.put(`/conversations/${vars.id}`, { is_archived: vars.is_archived })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  // ---- 删除 ----
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/conversations/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  // ==================== 操作 ====================

  const handleToggleArchive = async (conv: Conversation) => {
    setActingId(conv.id)
    try {
      const next = !conv.is_archived
      await updateMutation.mutateAsync({ id: conv.id, is_archived: next })
      toast.success(next ? t('conversations.toastArchived') : t('conversations.toastUnarchived'))
    } catch {
      toast.error(t('conversations.toastArchiveFailed'))
    } finally {
      setActingId(null)
    }
  }

  const handleExport = async (conv: Conversation) => {
    setExportingId(conv.id)
    try {
      const response = await api.post(`/conversations/${conv.id}/export`, null, {
        params: { format: 'markdown' },
      })
      const md = extractMarkdown(response.data)
      downloadText(md, `${toFileName(conv.title)}.md`)
      toast.success(t('conversations.toastExported'))
    } catch {
      toast.error(t('conversations.toastExportFailed'))
    } finally {
      setExportingId(null)
    }
  }

  const handleDelete = async (conv: Conversation) => {
    const ok = await confirm({
      title: t('conversations.deleteTitle'),
      message: t('conversations.deleteMessage', { title: conv.title }),
      confirmText: t('conversations.delete'),
      cancelText: t('common:actions.cancel'),
      variant: 'danger',
    })
    if (!ok) return
    setActingId(conv.id)
    try {
      await deleteMutation.mutateAsync(conv.id)
      if (selectedId === conv.id) setSelectedId(null)
      toast.success(t('conversations.toastDeleted'))
    } catch {
      toast.error(t('conversations.toastDeleteFailed'))
    } finally {
      setActingId(null)
    }
  }

  const listError = error ? getErrorMessage(error, t('conversations.loadFailed')) : ''

  // 继续对话：跳转到 AgentChatPage 并带上 cid，由该页加载历史消息后可接着提问
  const handleContinue = (conv: Conversation) => {
    navigate(`/agent?cid=${conv.id}`)
  }

  // ==================== 渲染 ====================

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('conversations.title')}</h1>
          <p className="text-muted text-sm">{t('conversations.subtitle')}</p>
        </div>
      </div>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={!archived}
          className={`tab-item${!archived ? ' active' : ''}`}
          onClick={() => setArchived(false)}
        >
          {t('conversations.tabActive')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={archived}
          className={`tab-item${archived ? ' active' : ''}`}
          onClick={() => setArchived(true)}
        >
          {t('conversations.tabArchived')}
        </button>
      </div>

      {/* 搜索框：后端按标题 + 消息内容检索，350ms 防抖 */}
      <div className="search-box" style={{ marginBottom: 12 }}>
        <ICONS.search size={16} />
        <input
          type="text"
          className="input"
          placeholder={t('common:actions.search')}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ flex: 1 }}
        />
        {searchTerm && (
          <button
            type="button"
            className="link"
            onClick={() => setSearchTerm('')}
            title={t('conversations.clearSearch')}
            style={{ padding: '0 0.5rem' }}
          >
            <ICONS.close size={14} />
          </button>
        )}
        {!isLoading && total > 0 && (
          <span className="text-muted text-sm" style={{ whiteSpace: 'nowrap', padding: '0 0.5rem' }}>
            {t('conversations.totalCount', { count: total })}
          </span>
        )}
      </div>

      {listError && (
        <div className="alert alert-error mb-4" role="alert">
          {listError}
        </div>
      )}

      {isLoading ? (
        <Loading text={t('conversations.listLoading')} />
      ) : conversations.length === 0 ? (
        <EmptyState
          icon="empty"
          title={
            archived
              ? t('conversations.emptyArchivedTitle')
              : t('conversations.emptyActiveTitle')
          }
          description={
            archived
              ? t('conversations.emptyArchivedDesc')
              : t('conversations.emptyActiveDesc')
          }
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('conversations.colTitle')}</th>
                <th>{t('conversations.colMessages')}</th>
                <th>{t('conversations.colCreated')}</th>
                <th>{t('conversations.colUpdated')}</th>
                <th>{t('conversations.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((conv) => {
                const busy = actingId === conv.id || exportingId === conv.id
                return (
                  <tr key={conv.id}>
                    <td>
                      <button
                        type="button"
                        className="link"
                        onClick={() => setSelectedId(conv.id)}
                        title={t('conversations.view')}
                      >
                        {conv.title || <span className="text-muted">{t('conversations.unnamed')}</span>}
                      </button>
                      {conv.is_archived && (
                        <span className="badge draft" style={{ marginLeft: 8 }}>
                          {t('conversations.archivedBadge')}
                        </span>
                      )}
                    </td>
                    <td>{t('conversations.messagesUnit', { count: conv.message_count })}</td>
                    <td>{formatDateTime(conv.created_at)}</td>
                    <td>{formatDateTime(conv.updated_at)}</td>
                    <td>
                      <div className="action-group">
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleContinue(conv)}
                          disabled={busy}
                          title={t('conversations.continue')}
                        >
                          {t('conversations.continue')}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => setSelectedId(conv.id)}
                          disabled={busy}
                        >
                          {t('conversations.view')}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleToggleArchive(conv)}
                          disabled={busy}
                        >
                          {conv.is_archived
                            ? t('conversations.unarchive')
                            : t('conversations.archive')}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleExport(conv)}
                          disabled={busy}
                          title={t('conversations.export')}
                        >
                          <ICONS.download size={14} />
                          {exportingId === conv.id ? t('conversations.exporting') : t('conversations.export')}
                        </button>
                        <button
                          type="button"
                          className="danger"
                          onClick={() => handleDelete(conv)}
                          disabled={busy}
                        >
                          {t('conversations.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {hasNextPage && (
            <div style={{ textAlign: 'center', padding: '1rem 0' }}>
              <button
                type="button"
                className="secondary"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage ? t('conversations.loadingMoreInProgress') : t('conversations.loadingMore')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 详情 Modal */}
      {selectedId && (
        <Modal
          title={t('conversations.detailTitle')}
          onClose={() => setSelectedId(null)}
          footer={
            <div className="action-group">
              {detail && !detail.is_archived && (
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    navigate(`/agent?cid=${detail.id}`)
                  }}
                >
                  {t('conversations.continue')}
                </button>
              )}
              <button type="button" className="secondary" onClick={() => setSelectedId(null)}>
                {t('common:actions.close')}
              </button>
            </div>
          }
        >
          {detailLoading || !detail ? (
            <Loading text={t('conversations.detailLoading')} />
          ) : (
            <>
              <div className="detail-group">
                <span className="detail-label">{detail.title}</span>
                <p className="text-muted text-sm">
                  {t('conversations.messagesUnit', { count: detail.message_count })}
                  {' · '}
                  {formatDateTime(detail.created_at)}
                </p>
              </div>

              {detail.messages.length === 0 ? (
                <EmptyState size="sm" title={t('conversations.detailEmpty')} />
              ) : (
                <div className="chat-messages" style={{ maxHeight: '52vh' }}>
                  {detail.messages.map((msg, idx) => {
                    const isUser = msg.role === 'user'
                    const roleLabel = isUser
                      ? t('conversations.roleUser')
                      : t('conversations.roleAgent')
                    return (
                      <div
                        key={`${idx}-${msg.timestamp}`}
                        className={`chat-message ${isUser ? 'user' : 'agent'}`}
                      >
                        <div className="chat-avatar">
                          <span className="chat-avatar-glyph">{roleLabel.slice(0, 1)}</span>
                        </div>
                        <div className="chat-content">
                          <span className="chat-time" style={{ marginBottom: 2 }}>
                            {roleLabel}
                          </span>
                          {/* agent 消息用 Markdown 渲染（表格/代码块等），user 消息纯文本 */}
                          {isUser ? (
                            <div className="chat-bubble">{msg.content}</div>
                          ) : (
                            <div className="chat-bubble markdown-body">
                              <MarkdownRenderer content={msg.content} />
                            </div>
                          )}
                          <span className="chat-time">{formatDateTime(msg.timestamp)}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </Modal>
      )}
    </div>
  )
}
