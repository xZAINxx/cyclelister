import { NavLink, useLocation } from 'react-router-dom'
import { Camera, LayoutList } from 'lucide-react'
import EbayStatusPill from './EbayStatusPill'
import { isSupabaseConfigured, supabase } from '../auth/supabaseClient'

export default function AppShell({ children, session }) {
  const location = useLocation()

  const signOut = async () => {
    if (supabase) await supabase.auth.signOut()
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <img src="/icon.svg" alt="" className="brand-logo" width="28" height="28" />
          <span className="brand-name">CycleLister</span>
        </div>
        <div className="header-right">
          <EbayStatusPill />
          {isSupabaseConfigured && session && (
            <button className="btn-ghost btn-sm" onClick={signOut} title="Sign out">
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className="app-main" key={location.pathname === '/' ? 'capture' : 'other'}>
        {children}
      </main>

      <nav className="tab-bar" aria-label="Primary">
        <NavLink to="/" className={({ isActive }) => `tab ${isActive ? 'tab-active' : ''}`} end>
          <Camera size={22} />
          <span>Capture</span>
        </NavLink>
        <NavLink
          to="/drafts"
          className={({ isActive }) => `tab ${isActive ? 'tab-active' : ''}`}
        >
          <LayoutList size={22} />
          <span>Drafts</span>
        </NavLink>
      </nav>
    </div>
  )
}
