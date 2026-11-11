import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errMsg } from '../api/client'
import { Button, Card, DataTable, Select, StatusBadge } from '../components/ui'
import { useI18n } from '../i18n'

type Analysis = {
  columns: string[]; suggestions: Record<string, { column: string; confidence: number }>
  required_missing: string[]; file_hash: string; sheets: string[]; total_rows: number
  duplicate_file: { batch_id: number; file_name: string; imported_at: string } | null
}
type RawPreview = { columns: string[]; rows: Record<string, string>[]; total: number; page: number; sheets: string[] }

const REQUIRED = ['activity', 'quantity', 'unit'] as const
const JOB_TIMEOUT_MS = 15 * 60 * 1000

export default function ImportPage() {
  const { t } = useI18n()
  const fileRef = useRef<HTMLInputElement>(null)
  const fileRef2 = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [sheet, setSheet] = useState<string>('')
  const [sheets, setSheets] = useState<string[]>([])
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [raw, setRaw] = useState<RawPreview | null>(null)
  const [page, setPage] = useState(1)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [force, setForce] = useState(false)
  const [job, setJob] = useState<any>(null)
  const [elapsed, setElapsed] = useState(0)
  const [batches, setBatches] = useState<any[]>([])
  const pollRef = useRef<number | null>(null)
  const startRef = useRef<number>(0)

  const loadBatches = useCallback(() => api.get('/imports/batches').then((r) => setBatches(r.data)), [])
  useEffect(() => { loadBatches() }, [loadBatches])
  useEffect(() => () => { if (pollRef.current) window.clearInterval(pollRef.current) }, [])

  const resetForFile = () => {
    setAnalysis(null); setRaw(null); setJob(null); setMsg(''); setPage(1); setForce(false); setSheets([]); setSheet('')
  }

  const analyze = async (f: File, sheetName = '', pg = 1) => {
    setBusy(true); setMsg('')
    try {
      const fd = new FormData(); fd.append('file', f)
      if (sheetName) fd.append('sheet', sheetName)
      const r = await api.post('/imports/analyze', fd)
      setAnalysis(r.data)
      setSheets(r.data.sheets ?? [])
      if (!sheetName && r.data.sheet === null && r.data.sheets?.length === 1) setSheet(r.data.sheets[0])
      const fd2 = new FormData(); fd2.append('file', f)
      if (sheetName) fd2.append('sheet', sheetName)
      fd2.append('page', String(pg)); fd2.append('page_size', '100')
      const r2 = await api.post('/imports/raw-preview', fd2)
      setRaw(r2.data)
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  const pickFile = (f: File | null) => {
    if (!f) return
    setFile(f); resetForFile()
    analyze(f)
  }

  const changeSheet = async (name: string) => {
    setSheet(name); setPage(1); setJob(null)
    if (file) await analyze(file, name, 1)
  }

  const gotoPage = async (pg: number) => {
    if (!file) return
    setPage(pg)
    try {
      const fd = new FormData(); fd.append('file', file)
      if (sheet) fd.append('sheet', sheet)
      fd.append('page', String(pg)); fd.append('page_size', '100')
      const r = await api.post('/imports/raw-preview', fd)
      setRaw(r.data)
    } catch (e) { setMsg(errMsg(e)) }
  }

  const autoMapping = (): Record<string, string> => {
    const m: Record<string, string> = {}
    for (const [field, s] of Object.entries(analysis?.suggestions ?? {})) {
      if ((REQUIRED as readonly string[]).includes(field) || s.confidence >= 0.6) m[field] = s.column
    }
    return m
  }

  const missingRequired = (): string[] => {
    const m = autoMapping()
    return REQUIRED.filter((f) => !m[f])
  }

  const calculate = async () => {
    if (!file || !analysis) return
    const missing = missingRequired()
    if (missing.length) {
      setMsg(`${t('missingColumns')}: ${missing.join(', ')}. ${t('missingColumnsHint')}`)
      return
    }
    setMsg(''); setJob(null); setBusy(true)
    try {
      const fd = new FormData(); fd.append('file', file)
      fd.append('mapping', JSON.stringify(autoMapping()))
      fd.append('default_country', 'EG')
      if (sheet) fd.append('sheet', sheet)
      if (force) fd.append('force', 'true')
      const r = await api.post('/imports/jobs', fd)
      const jobId = r.data.job_id
      setJob({ job_id: jobId, status: 'queued', percent: 0, total: analysis.total_rows })
      startRef.current = Date.now()
      setElapsed(0)
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = window.setInterval(async () => {
        const secs = Math.round((Date.now() - startRef.current) / 1000)
        setElapsed(secs)
        if (Date.now() - startRef.current > JOB_TIMEOUT_MS) {
          window.clearInterval(pollRef.current!)
          setJob((j: any) => ({ ...j, status: 'timeout' }))
          return
        }
        try {
          const st = await api.get(`/imports/jobs/${jobId}`)
          setJob(st.data)
          if (st.data.status === 'done' || st.data.status === 'error') {
            window.clearInterval(pollRef.current!)
            loadBatches()
          }
        } catch (e) { setMsg(errMsg(e)) }
      }, 1000)
    } catch (e: any) {
      if (e?.response?.status === 409) {
        setMsg(`${t('duplicateFile')} — ${e.response.data?.detail?.previous_batch?.file_name ?? ''}. ${t('forceHint')}`)
      } else setMsg(errMsg(e))
    } finally { setBusy(false) }
  }

  const pages = raw ? Math.max(1, Math.ceil(raw.total / 100)) : 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('navImport')}</h1>
        <Button variant="outline" onClick={() => api.get('/imports/template.csv', { responseType: 'blob' }).then((r) => {
          const url = URL.createObjectURL(r.data)
          const a = document.createElement('a'); a.href = url; a.download = 'carbonai_import_template.csv'; a.click()
        })}>⬇ {t('downloadTemplate')}</Button>
      </div>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-600/20">{msg}</div>}

      <Card title={t('importFile')}>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            className="rounded-lg border border-dashed border-slate-300 px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-brand-50 file:px-3 file:py-1 file:text-brand-700" />
          <input ref={fileRef2} type="file" className="hidden" />
          {file && <span className="text-xs text-slate-500">{file.name} · {(file.size / 1024).toFixed(0)} KB</span>}
        </div>
        {analysis && (
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>{analysis.total_rows} {t('rows')}</span>
            {sheets.length > 1 && (
              <Select value={sheet} onChange={changeSheet} className="w-48"
                options={sheets.map((s) => ({ value: s, label: s }))} />
            )}
            {analysis.duplicate_file && (
              <span className="rounded bg-amber-100 px-2 py-0.5 font-medium text-amber-800">
                ⚠ {t('duplicateFile')}: {analysis.duplicate_file.file_name}
              </span>
            )}
            {missingRequired().length > 0 && (
              <span className="rounded bg-rose-100 px-2 py-0.5 font-medium text-rose-800">
                {t('missingColumns')}: {missingRequired().join(', ')}
              </span>
            )}
          </div>
        )}
      </Card>

      {raw && (
        <Card title={`${t('filePreview')} — ${t('page')} ${page}/${pages}`}
          actions={
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => gotoPage(page - 1)} disabled={page <= 1}>‹</Button>
              <Button variant="outline" onClick={() => gotoPage(page + 1)} disabled={page >= pages}>›</Button>
            </div>
          }>
          <div className="max-h-[420px] overflow-auto">
            <table className="min-w-full divide-y divide-slate-200 text-xs">
              <thead className="sticky top-0 bg-slate-50">
                <tr>{raw.columns.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1.5 text-start font-semibold text-slate-500">{c}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {raw.rows.map((row, i) => (
                  <tr key={i}>{raw.columns.map((c) => <td key={c} className="whitespace-nowrap px-2 py-1 text-slate-700">{row[c]}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              {t('forceImport')}
            </label>
            <Button className="ms-auto" onClick={calculate}
              disabled={busy || missingRequired().length > 0 || job?.status === 'running' || job?.status === 'queued'}>
              🧮 {t('calculateEmissions')}
            </Button>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">{t('autoMappingNote')}</p>
        </Card>
      )}

      {job && (
        <Card title={t('importProgress')}>
          <div className="space-y-2">
            <div className="flex items-center gap-3 text-sm">
              <StatusBadge status={job.status === 'done' ? 'approved' : job.status === 'error' || job.status === 'timeout' ? 'rejected' : 'submitted'} />
              <span className="text-slate-500">{job.phase}</span>
              <span className="tabular-nums">{job.percent ?? 0}%</span>
              <span className="ms-auto text-xs text-slate-400">{elapsed}s</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-brand-600 transition-all" style={{ width: `${job.percent ?? 0}%` }} />
            </div>
            <div className="text-xs text-slate-500">
              {t('total')}: {job.total ?? '—'} · {t('accepted')}: {job.added ?? 0} · {t('rejectedRows')}: {job.rejected ?? 0} · {t('failedRows')}: {job.failed ?? 0}
            </div>
            {job.error && <div className="rounded bg-rose-50 px-3 py-2 text-xs text-rose-700">{job.error}</div>}
            {job.status === 'timeout' && <div className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">{t('jobTimeout')}</div>}
            {job.result?.failed?.length > 0 && (
              <details className="rounded border border-slate-200 p-2 text-xs text-rose-700">
                <summary className="cursor-pointer">{t('rowErrors')} ({job.result.failed.length})</summary>
                <ul className="mt-1 space-y-0.5">
                  {job.result.failed.slice(0, 50).map(([n, why]: any) => <li key={n}>row {n}: {why}</li>)}
                </ul>
              </details>
            )}
            {job.status === 'done' && (
              <Button variant="outline" onClick={() => { setJob(null); setAnalysis(null); setRaw(null); setFile(null) }}>
                {t('newImport')}
              </Button>
            )}
          </div>
        </Card>
      )}

      {batches.length > 0 && (
        <Card title={t('batches')}>
          <DataTable rows={batches} pageSize={8} columns={[
            { key: 'batch_id', label: '#' },
            { key: 'file_name', label: 'File' },
            { key: 'imported_at', label: t('createdAt'), render: (r) => String(r.imported_at).slice(0, 19) },
            { key: 'rows_total', label: t('total') },
            { key: 'rows_accepted', label: t('accepted') },
            { key: 'rows_rejected', label: t('rejectedRows') },
            { key: 'rows_duplicate', label: t('duplicates') },
          ]} />
        </Card>
      )}
    </div>
  )
}
