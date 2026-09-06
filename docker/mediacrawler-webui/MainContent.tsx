import { Terminal } from '@/components/console/Terminal'
import { QrCodePanel } from '@/components/login/QrCodePanel'
import { useLogWebSocket } from '@/hooks/useWebSocket'

export function MainContent() {
  useLogWebSocket()

  return (
    <main className="flex-1 flex flex-col overflow-hidden min-h-0 relative z-10">
      <QrCodePanel />
      <Terminal />
    </main>
  )
}
