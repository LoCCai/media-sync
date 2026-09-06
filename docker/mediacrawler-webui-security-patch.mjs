import { readFileSync, writeFileSync } from 'node:fs'

const packagePath = 'package.json'
const manifest = JSON.parse(readFileSync(packagePath, 'utf8'))

if (manifest?.dependencies?.axios !== '^1.7.9') {
  throw new Error('unexpected pinned MediaCrawler Axios seam')
}
if (manifest.overrides !== undefined) {
  throw new Error('unexpected pinned MediaCrawler override seam')
}

// The locked upstream source predates fixes now required by npm audit. These
// exact build-only overrides affect the compiled browser bundle; the upstream
// checkout itself remains byte-for-byte clean and revision-qualified.
manifest.dependencies.axios = '1.18.0'
manifest.overrides = {
  'follow-redirects': '1.16.0',
  'form-data': '4.0.6',
}

writeFileSync(packagePath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
