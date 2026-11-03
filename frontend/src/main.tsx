import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { unlockAudio } from './audio'
import { ErrorBoundary } from './components/ErrorBoundary'
import { reportUncaughtErrors } from './errors'
import { enableCardTilt } from './tilt'

// audio starts on the first click or key press (browser autoplay rules)
unlockAudio()
reportUncaughtErrors()
enableCardTilt()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
