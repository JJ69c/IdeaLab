import { Routes, Route, Link } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Inject from './pages/Inject'
import Report from './pages/Report'
import Compare from './pages/Compare'
import BusinessPlan from './pages/BusinessPlan'
import LiveSimulation from './pages/LiveSimulation'

export default function App() {
  return (
    <Routes>
      {/* Landing page — full-screen, no nav */}
      <Route path="/" element={<Landing />} />

      {/* LiveSimulation is full-screen, no nav wrapper */}
      <Route path="/simulation/:id" element={<LiveSimulation />} />

      {/* Standard pages with nav */}
      <Route path="*" element={
        <div className="min-h-screen bg-background">
          <nav className="glass-panel border-b border-outline-variant/30 px-6 py-3 flex items-center gap-8">
            <Link to="/" className="text-xl font-bold text-primary">IdeaLab</Link>
            <Link to="/dashboard" className="text-sm text-on-surface-variant hover:text-on-surface transition-colors">Dashboard</Link>
            <Link to="/inject" className="text-sm text-on-surface-variant hover:text-on-surface transition-colors">New Simulation</Link>
          </nav>
          <main className="max-w-6xl mx-auto px-6 py-8">
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/inject" element={<Inject />} />
              <Route path="/report/:id" element={<Report />} />
              <Route path="/compare/:variantId" element={<Compare />} />
              <Route path="/business-plan/:id" element={<BusinessPlan />} />
            </Routes>
          </main>
        </div>
      } />
    </Routes>
  )
}
