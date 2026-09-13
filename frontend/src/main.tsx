import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { AuthGate } from './auth'
import { Login } from './views/Login'
import './theme.css'

const root = document.getElementById('root')
if (!root) throw new Error('No #root element in index.html')
createRoot(root).render(
  <StrictMode>
    <AuthGate signIn={(onSignedIn) => <Login onSignedIn={onSignedIn} />}>
      <App />
    </AuthGate>
  </StrictMode>,
)
