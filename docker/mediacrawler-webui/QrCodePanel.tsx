import { useEffect, useState } from 'react'
import { useCrawlerStore } from '@/store/crawlerStore'

export function QrCodePanel() {
  const status = useCrawlerStore((state) => state.status)
  const loginType = useCrawlerStore((state) => state.config.login_type)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const active = status === 'running' && loginType === 'qrcode'

  useEffect(() => {
    let stopped = false
    let currentUrl: string | null = null
    let currentDigest = ''

    const refresh = async () => {
      if (stopped) return
      try {
        const response = await fetch('/crawler/api/crawler/qrcode', {
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { Accept: 'image/png' },
        })
        if (!response.ok || stopped) {
          if (currentUrl !== null) {
            URL.revokeObjectURL(currentUrl)
            currentUrl = null
            currentDigest = ''
            setImageUrl(null)
          }
          return
        }
        const digest = response.headers.get('x-media-sync-qr-digest') ?? ''
        if (digest !== '' && digest === currentDigest) return
        const blob = await response.blob()
        if (blob.type !== 'image/png' || blob.size === 0 || stopped) return
        const nextUrl = URL.createObjectURL(blob)
        if (currentUrl !== null) URL.revokeObjectURL(currentUrl)
        currentUrl = nextUrl
        currentDigest = digest
        setImageUrl(nextUrl)
      } catch {
        // The QR is created asynchronously; keep polling until it exists.
      }
    }

    setImageUrl(null)
    if (!active) return
    void refresh()
    const timer = window.setInterval(() => void refresh(), 750)
    return () => {
      stopped = true
      window.clearInterval(timer)
      if (currentUrl !== null) URL.revokeObjectURL(currentUrl)
    }
  }, [active])

  if (!active) return null
  return (
    <section className="mb-3 flex items-center gap-4 rounded-lg border border-cyber-neon-cyan/30 bg-cyber-bg-tertiary/80 p-3">
      {imageUrl ? (
        <img className="h-40 w-40 rounded bg-white p-2" src={imageUrl} alt="平台登录二维码" />
      ) : (
        <div className="flex h-40 w-40 items-center justify-center rounded border border-dashed border-cyber-border-DEFAULT text-center text-xs text-cyber-text-muted">
          正在等待平台二维码…
        </div>
      )}
      <div className="text-xs leading-6 text-cyber-text-secondary">
        <strong className="block text-cyber-text-primary">使用对应平台 App 扫码</strong>
        二维码只在本次任务期间通过已认证页面显示，不会写入媒体目录。
      </div>
    </section>
  )
}
