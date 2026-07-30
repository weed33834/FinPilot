import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import type { Report, DataResponse, PaginatedResponse } from '../../types/report'
import ReportCreate from '../../components/ReportCreate'
import { ICONS } from '../../components/ui/Icons'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import BottomSheet from '../../components/mobile/BottomSheet'
import MobileCard from '../../components/mobile/MobileCard'
import '../../i18n/mobile'

const STATUS_KEY: Record<string, string> = {
  draft: 'common:reports.statusDraft',
  pending: 'common:reports.statusPending',
  processing: 'common:reports.statusProcessing',
  reviewing: 'common:reports.statusReviewing',
  approved: 'common:reports.statusApproved',
  rejected: 'common:reports.statusRejected',
  failed: 'common:reports.statusFailed',
}

/**
 * 移动端报告：单列卡片列表 + 底部新建弹层（与桌面表格/多栏不同的交互）。
 * 复用 react-query 列表查询与 ReportCreate 组件，点击进入 /reports/:id 复用桌面详情路由。
 */
export default function ReportsMobile() {
  const { t } = useTranslation(['common', 'mobile'])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  const {
    data: reports = [],
    isLoading: loading,
    error: listError,
  } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: async () => {
      const response = await api.get<DataResponse<PaginatedResponse<Report>>>('/reports', {
        params: { page: 1, page_size: 50 },
      })
      return response.data.data?.items || []
    },
  })

  const error = listError ? getErrorMessage(listError, t('common:reports.loadFailed')) : ''

  return (
    <div className="mreports">
      <MobilePageHeader
        title={t('common:reports.title')}
        right={
          <button
            type="button"
            className="mreports__add"
            aria-label={t('common:actions.create')}
            onClick={() => setCreateOpen(true)}
          >
            <ICONS.copy size={18} />
          </button>
        }
      />

      {error && (
        <div className="mreports__error" role="alert">
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="mreports__loading">{t('common:status.loading')}</div>
      ) : reports.length === 0 ? (
        <div className="mreports__empty">
          <ICONS.reports size={28} />
          <p>{t('common:reports.emptyTitle')}</p>
        </div>
      ) : (
        <div className="mreports__list">
          {reports.map((report) => (
            <MobileCard key={report.id} onClick={() => navigate(`/reports/${report.id}`)}>
              <div className="mreports__item-head">
                <span className="mreports__name">{report.title}</span>
                <span className="mreports__status">
                  {t(STATUS_KEY[report.status] || 'common:reports.statusDraft')}
                </span>
              </div>
              <div className="mreports__meta">
                {report.created_at ? new Date(report.created_at).toLocaleDateString() : ''}
              </div>
            </MobileCard>
          ))}
        </div>
      )}

      <BottomSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('common:actions.create')}
      >
        <ReportCreate
          onCreated={() => {
            setCreateOpen(false)
            void queryClient.invalidateQueries({ queryKey: ['reports'] })
          }}
        />
      </BottomSheet>
    </div>
  )
}
