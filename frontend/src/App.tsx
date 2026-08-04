import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ToastProvider } from './components/Toasts'
import { EmptyState } from './components/ui'
import { ComparePage } from './pages/ComparePage'
import { ComparisonPage } from './pages/ComparisonPage'
import { DossierPage } from './pages/DossierPage'
import { DossiersPage } from './pages/DossiersPage'
import { HomePage } from './pages/HomePage'
import { InboxPage } from './pages/InboxPage'
import { KnowledgePage } from './pages/KnowledgePage'
import { LibraryPage } from './pages/LibraryPage'
import { ReviewPage } from './pages/ReviewPage'
import { ReviewSourcePage } from './pages/ReviewSourcePage'
import { SearchPage } from './pages/SearchPage'
import { SettingsPage } from './pages/SettingsPage'
import { SourcePage } from './pages/SourcePage'

export function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/inbox/:sourceId/review" element={<ReviewSourcePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/library/:sourceId" element={<SourcePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/dossiers" element={<DossiersPage />} />
            <Route path="/dossiers/:dossierId" element={<DossierPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/compare/:comparisonId" element={<ComparisonPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={
                <EmptyState
                  icon="⌗"
                  title="Screen not found"
                  body="That address does not match any FORGE screen."
                />
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
