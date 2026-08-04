/** Shapes returned by the FORGE API. Kept in one place so a backend change
 *  surfaces as a type error rather than as a runtime surprise. */

export type SourceKind =
  | 'pdf'
  | 'text'
  | 'markdown'
  | 'csv'
  | 'json'
  | 'transcript'
  | 'image'
  | 'note'
  | 'web_article'

export type SourceStatus = 'processing' | 'needs_review' | 'ready' | 'error'

export type KnowledgeKind = 'insight' | 'rule' | 'hypothesis' | 'decision' | 'quote' | 'note'

export type TargetType =
  | 'source'
  | 'document'
  | 'excerpt'
  | 'knowledge'
  | 'entity'
  | 'dossier'
  | 'collection'
  | 'comparison'

export interface Tag {
  id: string
  slug: string
  name: string
  color: string | null
  description?: string | null
  usage_count?: number
}

export interface Source {
  id: string
  kind: SourceKind
  status: SourceStatus
  title: string
  author: string | null
  publisher: string | null
  source_url: string | null
  published_on: string | null
  language: string | null
  summary: string | null
  original_filename: string | null
  mime_type: string | null
  byte_size: number | null
  char_count: number
  word_count: number
  page_count: number | null
  imported_at: string
  updated_at: string
  reviewed_at: string | null
  is_demo: boolean
  extraction_method: string
  error_message: string | null
  content_hash: string
  tags: Tag[]
  excerpt_count: number
  has_original: boolean
}

export interface Locator {
  page?: number
  section?: string
  timestamp?: string
  timestamp_seconds?: number
  row_start?: number
  row_end?: number
  pointer?: string
  index?: number
  char_start?: number
  speaker?: string
  [key: string]: unknown
}

export interface DocumentUnit {
  id: string
  ordinal: number
  kind: string
  title: string | null
  text: string
  char_start: number
  char_end: number
  locator: Locator
  locator_label: string
}

export interface Provenance {
  source_id: string
  source_title: string
  source_kind?: string
  locator: Locator
  locator_label: string
  char_start: number | null
  char_end: number | null
  author: string | null
  published_on: string | null
  url: string | null
  extraction_method: string | null
  created_at: string | null
  citation: string
}

export interface Excerpt {
  id: string
  source_id: string
  document_id: string | null
  text: string
  note: string | null
  char_start: number | null
  char_end: number | null
  locator: Locator
  origin: string
  created_at: string
  provenance: Provenance | Record<string, never>
  used_by: Array<{ target_type: TargetType; target_id: string; label: string; kind: string; stance: string }>
}

export interface Evidence {
  id: string
  stance: string
  note: string | null
  excerpt_id: string
  text: string
  locator: Locator
  locator_label: string
  source_id: string | null
  source_title: string
  source_kind: string | null
}

export interface KnowledgeObject {
  id: string
  kind: KnowledgeKind
  title: string
  body: string
  status: string
  confidence: number | null
  origin: string
  generated_by: string | null
  generation_id: string | null
  review_due_on: string | null
  resolved_at: string | null
  outcome: string | null
  data: Record<string, unknown>
  is_demo: boolean
  created_at: string
  updated_at: string
  tags: Tag[]
  evidence: Evidence[]
}

export interface Entity {
  id: string
  kind: 'company' | 'ticker' | 'person' | 'topic' | 'theme'
  name: string
  normalized_name: string
  description: string | null
  aliases: string[]
  data: Record<string, unknown>
  is_demo: boolean
  created_at: string
  source_count: number
}

export interface DossierSummary {
  id: string
  slug: string
  title: string
  subject_kind: string
  status: string
  overview: string
  created_at: string
  updated_at: string
  is_demo: boolean
  tags: Tag[]
  counts: Record<string, number>
}

export interface DossierItem {
  id: string
  section: string
  position: number
  note: string | null
  target_type: TargetType
  target_id: string
  exists: boolean
  label: string
  sublabel: string
  kind: string
  source_id: string | null
}

export interface ClaimEvidence {
  id: string
  stance: string
  note: string | null
  excerpt_id: string | null
  source_id: string | null
  text?: string | null
  locator?: Locator
  source_title?: string | null
}

export interface Claim {
  id: string
  text: string
  stance: 'bull' | 'bear' | 'risk' | 'question' | 'neutral'
  confidence: number | null
  status: string
  position: number
  origin: string
  generated_by: string | null
  evidence: ClaimEvidence[]
}

export interface TimelineEvent {
  id: string
  occurred_on: string
  title: string
  description: string | null
  kind: string
  source_id: string | null
  source_title: string | null
}

export interface Neighbour {
  link_id: string
  relation: string
  direction: 'outgoing' | 'incoming'
  note: string | null
  origin: string
  target_type: TargetType
  target_id: string
  exists: boolean
  label: string
  sublabel: string
  kind: string
  source_id: string | null
}

export interface DossierDetail {
  dossier: DossierSummary & {
    thesis: string
    bull_case: string
    bear_case: string
    risks: string
    open_questions: string
    primary_entity_id: string | null
  }
  items: DossierItem[]
  claims: Claim[]
  timeline: TimelineEvent[]
  related_entities: Array<{ id: string; kind: string; name: string; via: string; sources: number }>
  linked_source_ids: string[]
  tags: Tag[]
  links: Neighbour[]
  knowledge_counts: Record<string, number>
  counts: Record<string, number>
}

export interface SearchHit {
  ref_type: TargetType
  ref_id: string
  source_id: string | null
  kind: string
  title: string
  snippet: string
  score: number
  exists: boolean
  subtitle: string
  origin?: string
  slug?: string
  tags?: string[]
  provenance: {
    source_id: string
    source_title: string
    author?: string | null
    published_on?: string | null
    locator_label: string
    char_start?: number
  } | null
}

export interface SearchResponse {
  query: string
  total: number
  limit: number
  offset: number
  results: SearchHit[]
  highlight: { start: string; end: string }
  index_size: number
  groups?: Array<{
    key: string
    source_id: string | null
    source_title: string | null
    source_kind: string | null
    best_score: number
    results: SearchHit[]
  }>
}

export interface ImportItemResult {
  status: 'created' | 'duplicate' | 'error' | 'rejected'
  filename: string | null
  source_id: string | null
  title: string | null
  message: string
  warnings: string[]
  duplicate_of_id: string | null
  duplicate_of_title: string | null
}

export interface ImportResponse {
  batch_id: string | null
  created: number
  duplicates: number
  errors: number
  rejected: number
  results: ImportItemResult[]
}

export interface EntityCandidate {
  kind: Entity['kind']
  name: string
  confidence: string
  count: number
  detector: string
  existing_id: string | null
  evidence?: string
  grounded?: boolean
}

export interface ReviewPayload {
  source: Source
  detected: Record<string, unknown> & {
    keywords?: string[]
    dates_in_text?: string[]
    language?: string | null
    title?: string | null
    author?: string | null
    published_on?: string | null
  }
  entity_candidates: EntityCandidate[]
  warnings: string[]
  preview: string
  documents: number
}

export interface InboxPayload {
  pending: Source[]
  failed: Source[]
  batches: Array<{ id: string; label: string; created_at: string; source_count: number }>
  ocr: { available: boolean; detail: string; enabled: boolean }
  limits: { max_upload_mb: number; max_batch_files: number }
}

export interface HomeStats {
  sources: number
  sources_by_kind: Record<string, number>
  needs_review: number
  errors: number
  excerpts: number
  knowledge: number
  knowledge_by_kind: Record<string, number>
  dossiers: number
  entities: number
  tags: number
  links: number
  words_indexed: number
}

export interface HomePayload {
  stats: HomeStats
  recent_sources: Array<{ id: string; title: string; kind: string; status: string; imported_at: string; word_count: number }>
  recent_dossiers: Array<{ id: string; slug: string; title: string; subject_kind: string; status: string; updated_at: string; claims: number; items: number }>
  unprocessed: Array<{ id: string; title: string; kind: string; status: string; error_message: string | null; warnings: string[]; imported_at: string }>
  loose_ends: { sources_without_tags: number; excerpts_not_used: number; knowledge_without_evidence: number }
}

export interface Suggestion {
  kind: string
  basis: string
  explanation: string
  score: number
  from: { target_type: TargetType; target_id: string; label: string }
  to: { target_type: TargetType; target_id: string; label: string }
  suggested_action: string
}

export interface ReviewDashboard {
  generated_at: string
  window_days: number
  recent_imports: HomePayload['recent_sources']
  unprocessed: HomePayload['unprocessed']
  open_hypotheses: Array<{ id: string; title: string; status: string; confidence: number | null; age_days: number; evidence_count: number; review_due_on: string | null }>
  recent_dossiers: HomePayload['recent_dossiers']
  awaiting_review: Array<{ id: string; kind: string; title: string; status: string; review_due_on: string | null; overdue_days: number | null; due_in_days: number | null }>
  suggestions: Suggestion[]
  loose_ends: HomePayload['loose_ends']
  disclaimer: string
}

export interface ComparisonSummary {
  id: string
  title: string
  subject_type: TargetType
  description: string | null
  is_demo: boolean
  updated_at: string
  subject_count: number
  dimension_count: number
}

export interface ComparisonCell {
  id: string
  text_value: string | null
  numeric_value: string | null
  boolean_value: boolean | null
  excerpt_id: string | null
  origin: string
}

export interface ComparisonDetail {
  id: string
  title: string
  subject_type: TargetType
  description: string | null
  is_demo: boolean
  updated_at: string
  subjects: Array<{ id: string; position: number; label: string; target_type: TargetType; target_id: string; exists: boolean; sublabel: string; kind: string }>
  dimensions: Array<{ id: string; name: string; kind: string; unit: string | null; higher_is_better: boolean; weight: string; position: number }>
  cells: Record<string, ComparisonCell>
  rankings: Record<string, string[]>
}

export interface SettingsPayload {
  values: Record<string, unknown>
  schema: Array<{
    key: string
    default: unknown
    type: 'bool' | 'text' | 'choice' | 'list'
    label: string
    help: string
    group: string
    choices: string[]
  }>
}

export interface SystemInfo {
  version: string
  python: string
  platform: string
  data_dir: string
  database_path: string
  files_dir: string
  backups_dir: string
  max_upload_mb: number
  migration: { current: string | null; head: string | null }
  storage: { file_count: number; total_bytes: number; database_bytes: number }
  index_size: number
  ocr: { available: boolean; detail: string; binary: string | null; version: string | null }
  llm: { name: string; available: boolean; detail: string; models: string[]; base_url: string | null }
  semantic: { enabled: boolean; available: boolean; detail: string; model: string; indexed: number }
}

export interface IntelligenceStatus {
  enabled: boolean
  provider: SystemInfo['llm']
  model: string
  operations: Array<{ key: string; label: string; has_deterministic_fallback: boolean }>
  policy: string
}

export interface OperationOutput {
  operation: string
  method: 'deterministic' | 'generated'
  generated: boolean
  provider: string
  model: string | null
  items: Array<Record<string, unknown>>
  text: string
  notice: string
  generation_id: string | null
  sources: string[]
  fallback_reason: string | null
}

export interface BackupInfo {
  name: string
  size_bytes: number
  created_at: string
  manifest: Record<string, unknown> & { counts?: Record<string, number>; label?: string; file_count?: number }
}

export interface IntegrityReport {
  dangling_references: Array<{ table: string; row_id: string; target_type: string; target_id: string }>
  missing_original_files: Array<{ source_id: string; title: string; path: string | null }>
  index: { entries: number; expected: number }
  healthy: boolean
}

export interface Paged<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
  pages?: number
  facets?: Record<string, Record<string, number>>
}
