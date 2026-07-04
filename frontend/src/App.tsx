import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import Spinner from './components/ui/Spinner';
import AIAssistant from './components/AIAssistant.jsx';

// ============================================================================
// AI Operating System routes  (Mission Control → Observe → Understand →
// Predict → Recommend → Act → Learn). Existing Route Intelligence pages are
// kept and reachable from the Understand section.
// ============================================================================

const MissionControl  = lazy(() => import('./pages/MissionControl.tsx'));
const LiveThinking    = lazy(() => import('./pages/LiveThinking.tsx'));
const Observe         = lazy(() => import('./pages/Observe.tsx'));
const Understand      = lazy(() => import('./pages/Understand.tsx'));
const Predict         = lazy(() => import('./pages/Predict.tsx'));
const Recommend       = lazy(() => import('./pages/Recommend.tsx'));
const Act             = lazy(() => import('./pages/Act.tsx'));
const Learn           = lazy(() => import('./pages/Learn.tsx'));
const Settings        = lazy(() => import('./pages/Settings.tsx'));
const Logs            = lazy(() => import('./pages/Logs.tsx'));

// Route Intelligence — preserved exactly as it was, now nested under "Understand".
const RouteIntelligence         = lazy(() => import('./pages/RouteIntelligence.jsx'));
const RouteIntelligenceUpload   = lazy(() => import('./pages/RouteIntelligenceUpload.jsx'));
const RouteIntelligenceTrip     = lazy(() => import('./pages/RouteIntelligenceTrip.jsx'));
const RouteIntelligenceSegment  = lazy(() => import('./pages/RouteIntelligenceSegment.jsx'));
const RouteIntelligenceCompare  = lazy(() => import('./pages/RouteIntelligenceCompare.jsx'));
const RouteIntelligenceInsights = lazy(() => import('./pages/RouteIntelligenceInsights.jsx'));

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-0)', color: 'var(--fg-1)' }}>
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <Suspense fallback={<Spinner />}>
              <Routes>
                {/* Default → Mission Control (the AI-OS landing page). */}
                <Route path="/" element={<Navigate to="/mission-control" replace />} />

                {/* AI-OS — primary intelligence loop */}
                <Route path="/mission-control" element={<MissionControl />} />
                <Route path="/live-thinking"   element={<LiveThinking />} />
                <Route path="/observe"         element={<Observe />} />
                <Route path="/understand"      element={<Understand />} />
                <Route path="/predict"         element={<Predict />} />
                <Route path="/recommend"       element={<Recommend />} />
                <Route path="/act"             element={<Act />} />
                <Route path="/learn"           element={<Learn />} />

                {/* System — configuration, database bootstrap & live logs */}
                <Route path="/settings"        element={<Settings />} />
                <Route path="/logs"            element={<Logs />} />

                {/* Route Intelligence (kept) — upload-driven deep analysis */}
                <Route path="/route-intel"                       element={<RouteIntelligence />} />
                <Route path="/route-intel/uploads/:uploadId"     element={<RouteIntelligenceUpload />} />
                <Route path="/route-intel/trips/:tripId"         element={<RouteIntelligenceTrip />} />
                <Route path="/route-intel/segments/:segmentId"   element={<RouteIntelligenceSegment />} />
                <Route path="/route-intel/compare/:cmpId"        element={<RouteIntelligenceCompare />} />
                <Route path="/route-intel/insights"              element={<RouteIntelligenceInsights />} />

                {/* anything else → back to Mission Control */}
                <Route path="*" element={<Navigate to="/mission-control" replace />} />
              </Routes>
            </Suspense>
          </main>
        </div>
        {/* AI Assistant dock — visible everywhere; route-intel-specific behaviour stays in-component. */}
        <AIAssistant />
      </div>
    </BrowserRouter>
  );
}
