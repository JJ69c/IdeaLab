import { Routes, Route, Link } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Inject from './pages/Inject'
import Report from './pages/Report'
import Compare from './pages/Compare'
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
        <div className="min-h-screen">
          <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-8">
            <Link to="/" className="text-xl font-bold text-indigo-600">IdeaLab</Link>
            <Link to="/dashboard" className="text-sm text-gray-600 hover:text-gray-900">Dashboard</Link>
            <Link to="/inject" className="text-sm text-gray-600 hover:text-gray-900">New Simulation</Link>
          </nav>
          <main className="max-w-6xl mx-auto px-6 py-8">
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/inject" element={<Inject />} />
              <Route path="/report/:id" element={<Report />} />
              <Route path="/compare/:variantId" element={<Compare />} />
            </Routes>
          </main>
        </div>
      } />
    </Routes>
  )
}
