import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import SignInGate from './auth/SignInGate'
import { isSupabaseConfigured, supabase } from './auth/supabaseClient'
import CaptureScreen from './screens/CaptureScreen'
import DashboardScreen from './screens/DashboardScreen'
import DraftsScreen from './screens/DraftsScreen'
import ReviewScreen from './screens/ReviewScreen'

export default function App() {
  // When auth isn't configured we skip the gate entirely (dev mode).
  const [authReady, setAuthReady] = useState(!isSupabaseConfigured)
  const [session, setSession] = useState(null)

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) return
    let alive = true

    supabase.auth.getSession().then(({ data }) => {
      if (!alive) return
      setSession(data.session)
      setAuthReady(true)
    })

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession)
      setAuthReady(true)
    })

    return () => {
      alive = false
      sub?.subscription?.unsubscribe?.()
    }
  }, [])

  if (isSupabaseConfigured) {
    if (!authReady) {
      return (
        <div className="fullscreen-center">
          <div className="spinner" aria-label="Loading" />
        </div>
      )
    }
    if (!session) return <SignInGate />
  }

  return (
    <AppShell session={session}>
      <Routes>
        <Route path="/" element={<CaptureScreen />} />
        <Route path="/drafts" element={<DraftsScreen />} />
        <Route path="/dashboard" element={<DashboardScreen />} />
        <Route path="/review/:id" element={<ReviewScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
