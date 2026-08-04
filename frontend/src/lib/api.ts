/**
 * Typed HTTP client.
 *
 * All network access goes through here so components never build URLs or parse
 * error envelopes themselves. Errors are normalised into `ApiError`, which
 * carries the message the backend wants the user to read.
 */

import type {
  BackupInfo,
  ComparisonDetail,
  ComparisonSummary,
  DocumentUnit,
  DossierDetail,
  DossierSummary,
  Entity,
  Excerpt,
  HomePayload,
  ImportResponse,
  InboxPayload,
  IntegrityReport,
  IntelligenceStatus,
  KnowledgeObject,
  Neighbour,
  OperationOutput,
  Paged,
  ReviewDashboard,
  ReviewPayload,
  SearchResponse,
  SettingsPayload,
  Source,
  SystemInfo,
  Tag,
  TargetType,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly problems: string[]

  constructor(message: string, status: number, problems: string[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problems = problems
  }
}

export type QueryValue = string | number | boolean | undefined | null | Array<string | number>

export function buildQuery(params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null && item !== '') search.append(key, String(item))
      }
    } else {
      search.append(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function toError(response: Response): Promise<ApiError> {
  let detail = `${response.status} ${response.statusText}`
  let problems: string[] = []
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') detail = body.detail
    else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
    if (Array.isArray(body?.problems)) problems = body.problems
  } catch {
    /* response had no JSON body; keep the status line */
  }
  return new ApiError(detail, response.status, problems)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
    })
  } catch (cause) {
    throw new ApiError(
      'Cannot reach the FORGE backend. Is it running? (.\\run.ps1 starts both processes.)',
      0,
      [String(cause)],
    )
  }
  if (!response.ok) throw await toError(response)
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return (await response.json()) as T
  return (await response.text()) as unknown as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body) })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

export interface LibraryFilters {
  q?: string
  kind?: string[]
  status?: string[]
  tag?: string[]
  entity_id?: string[]
  author?: string
  language?: string
  date_field?: string
  date_from?: string
  date_to?: string
  sort?: string
  page?: number
  page_size?: number
}

export const api = {
  health: () => get<{ status: string; version: string; index_size: number }>('/api/health'),
  home: () => get<HomePayload>('/api/home'),
  stats: () => get<HomePayload['stats'] & { storage: SystemInfo['storage']; index_size: number }>('/api/stats'),
  vocabulary: () => get<Record<string, unknown>>('/api/meta/vocabulary'),

  // --- inbox / import ---
  inbox: () => get<InboxPayload>('/api/inbox'),
  importFiles: (files: File[], options: { kind?: string; force?: boolean; batchLabel?: string } = {}) => {
    const form = new FormData()
    for (const file of files) form.append('files', file, file.name)
    if (options.kind) form.append('kind', options.kind)
    if (options.force) form.append('force', 'true')
    if (options.batchLabel) form.append('batch_label', options.batchLabel)
    return request<ImportResponse>('/api/import/files', { method: 'POST', body: form })
  },
  importText: (payload: {
    text: string
    kind?: string
    title?: string
    author?: string
    source_url?: string
    published_on?: string
    tags?: string[]
    force?: boolean
  }) => post<ImportResponse>('/api/import/text', payload),
  reviewPayload: (id: string) => get<ReviewPayload>(`/api/sources/${id}/review`),
  submitReview: (id: string, payload: Record<string, unknown>) => post<Source>(`/api/sources/${id}/review`, payload),
  reprocess: (id: string, ocr = false) => post<Source>(`/api/sources/${id}/reprocess${buildQuery({ ocr })}`),

  // --- library ---
  sources: (filters: LibraryFilters = {}) =>
    get<Paged<Source>>(`/api/sources${buildQuery(filters as Record<string, QueryValue>)}`),
  source: (id: string) => get<Source>(`/api/sources/${id}`),
  sourceDetail: (id: string) =>
    get<{
      source: Source
      detected_metadata: Record<string, unknown>
      warnings: string[]
      documents: DocumentUnit[]
      excerpts: Excerpt[]
      entities: Array<{ id: string; kind: string; name: string; count: number; confirmed: boolean; detector: string }>
      links: Neighbour[]
    }>(`/api/sources/${id}/detail`),
  sourceText: (id: string, offset = 0, limit = 40000) =>
    get<{ source_id: string; offset: number; limit: number; char_count: number; text: string; has_more: boolean }>(
      `/api/sources/${id}/text${buildQuery({ offset, limit })}`,
    ),
  updateSource: (id: string, payload: Record<string, unknown>) => patch<Source>(`/api/sources/${id}`, payload),
  deleteSource: (id: string) => del<{ deleted: string }>(`/api/sources/${id}`),
  setSourceTags: (id: string, tags: string[]) => put<{ tags: Tag[] }>(`/api/sources/${id}/tags`, { tags }),
  fileUrl: (id: string, download = false) => `/api/sources/${id}/file${buildQuery({ download })}`,

  // --- excerpts ---
  excerpts: (params: { q?: string; unused_only?: boolean; limit?: number; offset?: number } = {}) =>
    get<Paged<Excerpt>>(`/api/excerpts${buildQuery(params as Record<string, QueryValue>)}`),
  sourceExcerpts: (id: string) => get<Paged<Excerpt>>(`/api/sources/${id}/excerpts`),
  createExcerpt: (sourceId: string, payload: Record<string, unknown>) =>
    post<Excerpt>(`/api/sources/${sourceId}/excerpts`, payload),
  updateExcerpt: (id: string, payload: Record<string, unknown>) => patch<Excerpt>(`/api/excerpts/${id}`, payload),
  deleteExcerpt: (id: string) => del<{ deleted: string }>(`/api/excerpts/${id}`),
  promoteExcerpt: (id: string, payload: Record<string, unknown>) =>
    post<KnowledgeObject>(`/api/excerpts/${id}/promote`, payload),

  // --- knowledge ---
  knowledge: (params: Record<string, QueryValue> = {}) =>
    get<Paged<KnowledgeObject> & { statuses: Record<string, string[]> }>(`/api/knowledge${buildQuery(params)}`),
  knowledgeItem: (id: string) => get<KnowledgeObject>(`/api/knowledge/${id}`),
  knowledgeDetail: (id: string) =>
    get<{ knowledge: KnowledgeObject; links: Neighbour[]; allowed_statuses: string[] }>(`/api/knowledge/${id}/detail`),
  createKnowledge: (payload: Record<string, unknown>) => post<KnowledgeObject>('/api/knowledge', payload),
  updateKnowledge: (id: string, payload: Record<string, unknown>) =>
    patch<KnowledgeObject>(`/api/knowledge/${id}`, payload),
  deleteKnowledge: (id: string) => del<{ deleted: string }>(`/api/knowledge/${id}`),
  addEvidence: (id: string, payload: { excerpt_id: string; stance?: string; note?: string }) =>
    post<KnowledgeObject>(`/api/knowledge/${id}/evidence`, payload),
  removeEvidence: (id: string, linkId: string) => del<{ deleted: string }>(`/api/knowledge/${id}/evidence/${linkId}`),
  setKnowledgeTags: (id: string, tags: string[]) => put<{ tags: Tag[] }>(`/api/knowledge/${id}/tags`, { tags }),

  // --- graph ---
  entities: (params: Record<string, QueryValue> = {}) => get<Paged<Entity>>(`/api/entities${buildQuery(params)}`),
  entityDetail: (id: string) =>
    get<{ entity: Entity; sources: Source[]; links: Neighbour[] }>(`/api/entities/${id}`),
  createEntity: (payload: Record<string, unknown>) => post<Entity>('/api/entities', payload),
  updateEntity: (id: string, payload: Record<string, unknown>) => patch<Entity>(`/api/entities/${id}`, payload),
  deleteEntity: (id: string) => del<{ deleted: string }>(`/api/entities/${id}`),
  tags: () => get<Paged<Tag>>('/api/tags'),
  deleteTag: (id: string) => del<{ deleted: string }>(`/api/tags/${id}`),
  links: (targetType: TargetType, targetId: string) =>
    get<{ items: Neighbour[]; relations: string[] }>(
      `/api/links${buildQuery({ target_type: targetType, target_id: targetId })}`,
    ),
  createLink: (payload: {
    from_type: TargetType
    from_id: string
    to_type: TargetType
    to_id: string
    relation: string
    note?: string
  }) => post<{ id: string }>('/api/links', payload),
  deleteLink: (id: string) => del<{ deleted: string }>(`/api/links/${id}`),

  // --- dossiers ---
  dossiers: (params: Record<string, QueryValue> = {}) =>
    get<Paged<DossierSummary>>(`/api/dossiers${buildQuery(params)}`),
  dossier: (id: string) => get<DossierDetail>(`/api/dossiers/${id}`),
  createDossier: (payload: Record<string, unknown>) => post<DossierSummary>('/api/dossiers', payload),
  updateDossier: (id: string, payload: Record<string, unknown>) =>
    patch<DossierSummary>(`/api/dossiers/${id}`, payload),
  deleteDossier: (id: string) => del<{ deleted: string }>(`/api/dossiers/${id}`),
  setDossierTags: (id: string, tags: string[]) => put<{ tags: Tag[] }>(`/api/dossiers/${id}/tags`, { tags }),
  addDossierItem: (id: string, payload: { target_type: TargetType; target_id: string; section?: string; note?: string }) =>
    post<{ id: string }>(`/api/dossiers/${id}/items`, payload),
  removeDossierItem: (id: string, itemId: string) => del<{ deleted: string }>(`/api/dossiers/${id}/items/${itemId}`),
  addClaim: (id: string, payload: Record<string, unknown>) => post<unknown>(`/api/dossiers/${id}/claims`, payload),
  updateClaim: (id: string, claimId: string, payload: Record<string, unknown>) =>
    patch<unknown>(`/api/dossiers/${id}/claims/${claimId}`, payload),
  deleteClaim: (id: string, claimId: string) => del<unknown>(`/api/dossiers/${id}/claims/${claimId}`),
  addClaimEvidence: (id: string, claimId: string, payload: Record<string, unknown>) =>
    post<unknown>(`/api/dossiers/${id}/claims/${claimId}/evidence`, payload),
  deleteClaimEvidence: (id: string, claimId: string, evidenceId: string) =>
    del<unknown>(`/api/dossiers/${id}/claims/${claimId}/evidence/${evidenceId}`),
  addEvent: (id: string, payload: Record<string, unknown>) => post<unknown>(`/api/dossiers/${id}/events`, payload),
  deleteEvent: (id: string, eventId: string) => del<unknown>(`/api/dossiers/${id}/events/${eventId}`),
  dossierMarkdown: (id: string) => get<string>(`/api/dossiers/${id}/export/preview`),
  dossierMarkdownUrl: (id: string) => `/api/dossiers/${id}/export/markdown`,
  dossierBundleUrl: (id: string) => `/api/dossiers/${id}/export/bundle`,

  // --- comparisons ---
  comparisons: () => get<Paged<ComparisonSummary>>('/api/comparisons'),
  comparison: (id: string) => get<ComparisonDetail>(`/api/comparisons/${id}`),
  createComparison: (payload: Record<string, unknown>) => post<ComparisonDetail>('/api/comparisons', payload),
  updateComparison: (id: string, payload: Record<string, unknown>) =>
    patch<ComparisonDetail>(`/api/comparisons/${id}`, payload),
  deleteComparison: (id: string) => del<{ deleted: string }>(`/api/comparisons/${id}`),
  addSubject: (id: string, payload: { target_type: TargetType; target_id: string; label?: string }) =>
    post<ComparisonDetail>(`/api/comparisons/${id}/subjects`, payload),
  removeSubject: (id: string, subjectId: string) =>
    del<ComparisonDetail>(`/api/comparisons/${id}/subjects/${subjectId}`),
  addDimension: (id: string, payload: Record<string, unknown>) =>
    post<ComparisonDetail>(`/api/comparisons/${id}/dimensions`, payload),
  removeDimension: (id: string, dimensionId: string) =>
    del<ComparisonDetail>(`/api/comparisons/${id}/dimensions/${dimensionId}`),
  setCell: (id: string, payload: Record<string, unknown>) =>
    put<ComparisonDetail>(`/api/comparisons/${id}/cells`, payload),
  comparisonMarkdownUrl: (id: string) => `/api/comparisons/${id}/export/markdown`,

  // --- search ---
  search: (params: Record<string, QueryValue>) => get<SearchResponse>(`/api/search${buildQuery(params)}`),
  suggest: (q: string) => get<{ items: string[] }>(`/api/search/suggest${buildQuery({ q })}`),
  semanticSearch: (q: string) =>
    get<{ enabled: boolean; available: boolean; detail: string; results: Array<Record<string, unknown>> }>(
      `/api/search/semantic${buildQuery({ q })}`,
    ),
  buildSemanticIndex: () => post<{ indexed: number; skipped: number; detail: string }>('/api/search/semantic/index'),
  clearSemanticIndex: () => del<{ removed: number }>('/api/search/semantic/index'),
  searchStatus: () =>
    get<{
      fulltext: { engine: string; indexed_objects: number; syntax: Array<{ example: string; meaning: string }> }
      semantic: SystemInfo['semantic']
    }>('/api/search/status'),
  reindex: () => post<{ total: number }>('/api/search/reindex'),

  // --- review ---
  review: (days = 7) => get<ReviewDashboard>(`/api/review${buildQuery({ days })}`),

  // --- settings / system ---
  settings: () => get<SettingsPayload>('/api/settings'),
  updateSettings: (values: Record<string, unknown>) => put<SettingsPayload>('/api/settings', { values }),
  resetSettings: () => post<SettingsPayload>('/api/settings/reset'),
  systemInfo: () => get<SystemInfo>('/api/settings/system'),

  // --- intelligence ---
  // `probe` contacts the local provider even when the feature is disabled.
  // Without it the call never touches the network, so screens stay instant.
  intelligenceStatus: (probe = false) =>
    get<IntelligenceStatus>(`/api/intelligence/status${buildQuery({ probe })}`),
  runOperation: (payload: Record<string, unknown>) => post<OperationOutput>('/api/intelligence/run', payload),

  // --- export / backup / maintenance ---
  exportJsonUrl: '/api/export/json',
  sourceMarkdownUrl: (id: string) => `/api/export/sources/${id}/markdown`,
  knowledgeMarkdownUrl: (id: string) => `/api/export/knowledge/${id}/markdown`,
  exportSources: async (sourceIds: string[], includeOriginals = true): Promise<Blob> => {
    const response = await fetch('/api/export/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_ids: sourceIds, include_originals: includeOriginals }),
    })
    if (!response.ok) throw await toError(response)
    return response.blob()
  },
  backups: () => get<{ items: BackupInfo[] }>('/api/backups'),
  createBackup: (label?: string) => post<BackupInfo>('/api/backups', { label }),
  restoreBackup: (name: string) => post<Record<string, unknown>>(`/api/backups/${encodeURIComponent(name)}/restore`),
  deleteBackup: (name: string) => del<{ deleted: string }>(`/api/backups/${encodeURIComponent(name)}`),
  backupDownloadUrl: (name: string) => `/api/backups/${encodeURIComponent(name)}/download`,
  restoreUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return request<Record<string, unknown>>('/api/backups/upload-restore', { method: 'POST', body: form })
  },
  integrity: () => get<IntegrityReport>('/api/maintenance/integrity'),
  seed: (reset = false) => post<Record<string, unknown>>('/api/maintenance/seed', { reset }),
  clearDemo: () => del<Record<string, number>>('/api/maintenance/demo'),
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
