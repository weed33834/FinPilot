import { useTranslation } from 'react-i18next'
import type {
  SubscriptionChannel,
  SubscriptionExportFormat,
  SubscriptionFrequency,
  SubscriptionReportType,
} from '../../types/reportSubscription.ts'
import Modal from '../../components/ui/Modal.tsx'
import {
  CHANNELS,
  EXPORT_FORMATS,
  FREQUENCIES,
  REPORT_TYPES,
  WEEKDAYS,
  type FormState,
} from './constants.ts'

interface SubscriptionFormModalProps {
  open: boolean
  editing: boolean
  form: FormState
  setForm: React.Dispatch<React.SetStateAction<FormState>>
  onSubmit: () => void
  onCancel: () => void
  submitting: boolean
  toggleChannel: (ch: SubscriptionChannel) => void
  error?: string
}

export default function SubscriptionFormModal({
  open,
  editing,
  form,
  setForm,
  onSubmit,
  onCancel,
  submitting,
  toggleChannel,
  error,
}: SubscriptionFormModalProps) {
  const { t } = useTranslation()
  if (!open) return null

  return (
    <Modal
      title={editing ? t('reportSubscriptions.editTitle') : t('reportSubscriptions.createTitle')}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="secondary" onClick={onCancel}>
            {t('actions.cancel')}
          </button>
          <button type="button" onClick={onSubmit} disabled={submitting || !form.name}>
            {submitting ? t('status.saving') : t('actions.save')}
          </button>
        </>
      }
    >
      {error && <div className="alert alert-error mb-3">{error}</div>}
      <div className="form-group">
        <label htmlFor="sub-name">{t('reportSubscriptions.name')}</label>
        <input
          id="sub-name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder={t('reportSubscriptions.namePlaceholder')}
        />
      </div>
      <div className="form-group">
        <label htmlFor="sub-report-type">{t('reportSubscriptions.reportType')}</label>
        <select
          id="sub-report-type"
          value={form.report_type}
          onChange={(e) =>
            setForm({ ...form, report_type: e.target.value as SubscriptionReportType })
          }
          disabled={editing}
        >
          {REPORT_TYPES.map((rt) => (
            <option key={rt.value} value={rt.value}>{t(rt.labelKey)}</option>
          ))}
        </select>
        {editing && (
          <small className="text-muted">{t('reportSubscriptions.reportTypeLocked')}</small>
        )}
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="sub-year">{t('reportSubscriptions.year')}</label>
          <input
            id="sub-year"
            type="number"
            value={form.year}
            onChange={(e) => setForm({ ...form, year: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label htmlFor="sub-period">{t('reportSubscriptions.period')}</label>
          <select
            id="sub-period"
            value={form.period}
            onChange={(e) => setForm({ ...form, period: e.target.value })}
          >
            <option value="Q1">Q1</option>
            <option value="Q2">Q2</option>
            <option value="Q3">Q3</option>
            <option value="Q4">Q4</option>
            <option value="H1">H1</option>
            <option value="H2">H2</option>
            <option value="annual">{t('reportSubscriptions.periodAnnual')}</option>
          </select>
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="sub-frequency">{t('reportSubscriptions.frequency')}</label>
        <select
          id="sub-frequency"
          value={form.frequency}
          onChange={(e) =>
            setForm({ ...form, frequency: e.target.value as SubscriptionFrequency })
          }
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>{t(f.labelKey)}</option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="sub-hour">{t('reportSubscriptions.atHour')}</label>
          <input
            id="sub-hour"
            type="number"
            min={0}
            max={23}
            value={form.at_hour}
            onChange={(e) => setForm({ ...form, at_hour: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label htmlFor="sub-minute">{t('reportSubscriptions.atMinute')}</label>
          <input
            id="sub-minute"
            type="number"
            min={0}
            max={59}
            value={form.at_minute}
            onChange={(e) => setForm({ ...form, at_minute: e.target.value })}
          />
        </div>
      </div>
      {form.frequency === 'weekly' && (
        <div className="form-group">
          <label htmlFor="sub-dow">{t('reportSubscriptions.dayOfWeek')}</label>
          <select
            id="sub-dow"
            value={form.day_of_week}
            onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}
          >
            {WEEKDAYS.map((key, idx) => (
              <option key={idx} value={idx}>{t(key)}</option>
            ))}
          </select>
        </div>
      )}
      {form.frequency === 'monthly' && (
        <div className="form-group">
          <label htmlFor="sub-dom">{t('reportSubscriptions.dayOfMonth')}</label>
          <input
            id="sub-dom"
            type="number"
            min={1}
            max={28}
            value={form.day_of_month}
            onChange={(e) => setForm({ ...form, day_of_month: e.target.value })}
          />
        </div>
      )}
      <div className="form-group">
        <label htmlFor="sub-export">{t('reportSubscriptions.exportFormat')}</label>
        <select
          id="sub-export"
          value={form.export_format}
          onChange={(e) =>
            setForm({ ...form, export_format: e.target.value as SubscriptionExportFormat })
          }
        >
          {EXPORT_FORMATS.map((f) => (
            <option key={f.value} value={f.value}>{t(f.labelKey)}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <span className="detail-label">{t('reportSubscriptions.channels')}</span>
        <div className="checkbox-group">
          {CHANNELS.map((ch) => (
            <label key={ch.value} className="checkbox-label">
              <input
                type="checkbox"
                checked={form.channels.includes(ch.value)}
                onChange={() => toggleChannel(ch.value)}
              />
              {t(ch.labelKey)}
            </label>
          ))}
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="sub-recipients">{t('reportSubscriptions.recipients')}</label>
        <input
          id="sub-recipients"
          value={form.recipients}
          onChange={(e) => setForm({ ...form, recipients: e.target.value })}
          placeholder={t('reportSubscriptions.recipientsPlaceholder')}
        />
      </div>
    </Modal>
  )
}
