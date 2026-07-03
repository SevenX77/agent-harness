import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './store/themeStore'
import { App } from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { configureApiToken } from './api/client'
import { bootstrapTunnelToken } from './config/tunnel-token'
import { i18nReady } from './i18n'

const token = bootstrapTunnelToken()
if (token) {
  configureApiToken(token)
}

await i18nReady

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary label="Studio">
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
