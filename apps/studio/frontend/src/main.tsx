import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { RuntimeGate } from './components/RuntimeGate'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RuntimeGate />
  </StrictMode>,
)
