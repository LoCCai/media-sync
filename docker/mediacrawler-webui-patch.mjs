import { readFileSync, writeFileSync } from 'node:fs'

function replaceExact(path, before, after) {
  const source = readFileSync(path, 'utf8').replaceAll('\r\n', '\n')
  const matches = source.split(before).length - 1
  if (matches !== 1) {
    throw new Error(`expected exactly one integration seam in ${path}, found ${matches}`)
  }
  writeFileSync(path, source.replace(before, after), 'utf8')
}

replaceExact('src/lib/api.ts', "baseURL: '/api',", "baseURL: '/crawler/api',")
replaceExact(
  'src/lib/api.ts',
  "})\n\n// Types",
  `})

let csrfTokenRequest: Promise<string> | null = null

async function operatorCsrfToken(): Promise<string> {
  if (csrfTokenRequest === null) {
    csrfTokenRequest = axios
      .get<{ csrf_token?: unknown }>('/api/v1/operator-auth/session', {
        withCredentials: true,
        headers: { Accept: 'application/json' },
      })
      .then(({ data }) => {
        if (typeof data.csrf_token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token)) {
          throw new Error('operator_session_invalid')
        }
        return data.csrf_token
      })
      .catch((error) => {
        csrfTokenRequest = null
        throw error
      })
  }
  return csrfTokenRequest
}

api.interceptors.request.use(async (request) => {
  const method = (request.method ?? 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) {
    request.headers.set('x-media-sync-csrf', await operatorCsrfToken())
  }
  return request
})

// Types`,
)
replaceExact(
  'src/lib/api.ts',
  "getDownloadUrl: (path: string) => `/api/data/download/${path}`",
  "getDownloadUrl: (path: string) => `/crawler/api/data/download/${path}`",
)
replaceExact('src/hooks/useWebSocket.ts', '/api/ws/logs', '/crawler/api/ws/logs')
replaceExact('index.html', 'href="/vite.svg"', 'href="/crawler/static/vite.svg"')

const footer = 'src/components/layout/AuthorFooter.tsx'
writeFileSync(footer, readFileSync(footer, 'utf8').replaceAll('src="/logos/', 'src="/crawler/logos/'), 'utf8')
