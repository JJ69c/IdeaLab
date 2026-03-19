import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface SimSummary {
  id: string
  idea_title: string
  status: string
  created_at: string
  metrics: {
    awareness_rate?: number
    interest_rate?: number
    adoption_likelihood?: number
  } | null
}

export default function Dashboard() {
  const [sims, setSims] = useState<SimSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/simulations')
      .then(r => r.json())
      .then(data => { setSims(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-gray-500">Loading...</p>

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Simulations</h1>
        <Link
          to="/inject"
          className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-indigo-700"
        >
          + New Simulation
        </Link>
      </div>

      {sims.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg mb-2">No simulations yet</p>
          <p className="text-sm">Inject your first idea to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {sims.map(sim => (
            <Link
              key={sim.id}
              to={sim.status === 'completed' ? `/report/${sim.id}` : `/simulation/${sim.id}`}
              className="block bg-white rounded-lg border border-gray-200 p-4 hover:border-indigo-300 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-semibold">{sim.idea_title}</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    {new Date(sim.created_at).toLocaleDateString()} &middot;{' '}
                    <span className={
                      sim.status === 'completed' ? 'text-green-600' :
                      sim.status === 'failed' ? 'text-red-600' : 'text-yellow-600'
                    }>
                      {sim.status}
                    </span>
                  </p>
                </div>
                {sim.metrics && (
                  <div className="flex gap-4 text-sm">
                    <div className="text-center">
                      <div className="text-gray-400">Awareness</div>
                      <div className="font-semibold">{((sim.metrics.awareness_rate ?? 0) * 100).toFixed(0)}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-gray-400">Interest</div>
                      <div className="font-semibold">{((sim.metrics.interest_rate ?? 0) * 100).toFixed(0)}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-gray-400">Adoption</div>
                      <div className="font-semibold">{((sim.metrics.adoption_likelihood ?? 0) * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
