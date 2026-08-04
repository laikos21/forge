import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, buildQuery } from './api'

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({}),
    text: async () => '',
    ...response,
  } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('buildQuery', () => {
  it('serialises scalars and arrays', () => {
    expect(buildQuery({ q: 'margin', kind: ['pdf', 'csv'], page: 2 })).toBe('?q=margin&kind=pdf&kind=csv&page=2')
  })

  it('drops empty values', () => {
    expect(buildQuery({ q: '', kind: [], author: undefined, tag: null })).toBe('')
  })

  it('encodes special characters', () => {
    expect(buildQuery({ q: '"gross margin" -crypto' })).toContain('q=%22gross+margin%22+-crypto')
  })
})

describe('request handling', () => {
  it('returns parsed JSON on success', async () => {
    mockFetch({ json: async () => ({ status: 'ok', version: '0.1.0', index_size: 12 }) })
    await expect(api.health()).resolves.toEqual({ status: 'ok', version: '0.1.0', index_size: 12 })
  })

  it('raises ApiError carrying the backend detail', async () => {
    mockFetch({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'status must be one of [open]', problems: ['status'] }),
    })
    await expect(api.knowledgeItem('x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      message: 'status must be one of [open]',
      problems: ['status'],
    })
  })

  it('falls back to the status line when the body is not JSON', async () => {
    mockFetch({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => {
        throw new Error('not json')
      },
    })
    await expect(api.health()).rejects.toThrow('500 Internal Server Error')
  })

  it('explains an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await api.health().catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
    expect((error as ApiError).message).toContain('Cannot reach the FORGE backend')
  })

  it('sends JSON bodies with the right content type', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await api.createDossier({ title: 'X' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ title: 'X' })
  })

  it('sends uploads as multipart without forcing a content type', async () => {
    const fetchMock = mockFetch({ json: async () => ({ created: 1, results: [] }) })
    const file = new File(['hello'], 'note.md', { type: 'text/markdown' })
    await api.importFiles([file], { batchLabel: 'test' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/import/files')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers['Content-Type']).toBeUndefined()
  })
})

describe('url builders', () => {
  it('builds file and export urls', () => {
    expect(api.fileUrl('abc', true)).toBe('/api/sources/abc/file?download=true')
    expect(api.dossierMarkdownUrl('d1')).toBe('/api/dossiers/d1/export/markdown')
    expect(api.backupDownloadUrl('a b.zip')).toBe('/api/backups/a%20b.zip/download')
  })
})
