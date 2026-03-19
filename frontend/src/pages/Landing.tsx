import { useEffect, useRef, useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

// ── Network graph animation (replaces DNA helix) ──────────────────────
// Nodes float in 3D space, connected by lines. Periodic "activation waves"
// spread outward from random seeds — a visual metaphor for idea propagation.

interface Node {
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  radius: number
  activation: number // 0-1, how "activated" (idea-aware) the node is
  activationDecay: number
}

function initNetwork(
  canvas: HTMLCanvasElement,
  densityMultiplier = 1,
  alignment = 0.5,
) {
  const ctx = canvas.getContext('2d')!
  let t = 0
  let animId: number
  const nodes: Node[] = []
  const connectionDist = 180
  const nodeCount = Math.floor(50 * densityMultiplier)

  function resize() {
    canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1)
    canvas.height = canvas.offsetHeight * (window.devicePixelRatio || 1)
    ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1)
  }

  window.addEventListener('resize', resize)
  resize()

  const logicalW = () => canvas.offsetWidth
  const logicalH = () => canvas.offsetHeight

  // Seed nodes in a loose 3D cloud
  for (let i = 0; i < nodeCount; i++) {
    nodes.push({
      x: (Math.random() - 0.5) * logicalW() * 0.7,
      y: (Math.random() - 0.5) * logicalH() * 0.8,
      z: (Math.random() - 0.5) * 400,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      vz: (Math.random() - 0.5) * 0.15,
      radius: 2 + Math.random() * 3,
      activation: 0,
      activationDecay: 0.003 + Math.random() * 0.005,
    })
  }

  // Periodic activation wave
  let waveTimer = 0
  const waveInterval = 180 // frames between waves

  function triggerWave() {
    const seed = nodes[Math.floor(Math.random() * nodes.length)]
    seed.activation = 1

    // Spread to nearby nodes with delay
    nodes.forEach(n => {
      const dx = n.x - seed.x
      const dy = n.y - seed.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < connectionDist * 1.5 && n !== seed) {
        setTimeout(() => { n.activation = Math.max(n.activation, 0.7) }, dist * 3)
      }
    })
  }

  function animate() {
    const lw = logicalW()
    const lh = logicalH()
    ctx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0)
    ctx.clearRect(0, 0, lw, lh)
    t += 0.005

    waveTimer++
    if (waveTimer > waveInterval) {
      waveTimer = 0
      triggerWave()
    }

    const fov = 800
    const cx = lw * alignment
    const cy = lh * 0.5

    // Project nodes
    const projected: { sx: number; sy: number; scale: number; idx: number }[] = []
    nodes.forEach((n, idx) => {
      // Gentle drift
      n.x += n.vx + Math.sin(t + idx * 0.3) * 0.1
      n.y += n.vy + Math.cos(t + idx * 0.4) * 0.1
      n.z += n.vz

      // Soft boundary
      if (Math.abs(n.x) > lw * 0.45) n.vx *= -0.8
      if (Math.abs(n.y) > lh * 0.45) n.vy *= -0.8
      if (Math.abs(n.z) > 250) n.vz *= -0.8

      // Decay activation
      n.activation = Math.max(0, n.activation - n.activationDecay)

      const scale = fov / (fov + n.z)
      projected.push({
        sx: cx + n.x * scale,
        sy: cy + n.y * scale,
        scale,
        idx,
      })
    })

    // Draw connections first (behind nodes)
    projected.forEach((p1, i) => {
      for (let j = i + 1; j < projected.length; j++) {
        const p2 = projected[j]
        const dx = p1.sx - p2.sx
        const dy = p1.sy - p2.sy
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < connectionDist * Math.min(p1.scale, p2.scale) * 1.2) {
          const n1 = nodes[p1.idx]
          const n2 = nodes[p2.idx]
          const avgActivation = (n1.activation + n2.activation) / 2
          const alpha = (1 - dist / (connectionDist * 1.2)) * 0.15 + avgActivation * 0.3
          ctx.strokeStyle = avgActivation > 0.3
            ? `rgba(79, 70, 229, ${alpha})` // indigo when activated
            : `rgba(0, 0, 0, ${alpha * 0.6})`
          ctx.lineWidth = 0.5 + avgActivation
          ctx.beginPath()
          ctx.moveTo(p1.sx, p1.sy)
          ctx.lineTo(p2.sx, p2.sy)
          ctx.stroke()
        }
      }
    })

    // Draw nodes
    projected.forEach(p => {
      const n = nodes[p.idx]
      const r = n.radius * p.scale
      const activation = n.activation

      if (activation > 0.1) {
        // Glow ring for activated nodes
        const glowR = r + 4 * activation
        ctx.beginPath()
        ctx.arc(p.sx, p.sy, glowR, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(79, 70, 229, ${activation * 0.2})`
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      const baseAlpha = p.scale > 0.8 ? 0.8 : 0.3
      ctx.fillStyle = activation > 0.3
        ? `rgba(79, 70, 229, ${baseAlpha + activation * 0.2})`
        : `rgba(0, 0, 0, ${baseAlpha})`
      ctx.fill()
    })

    animId = requestAnimationFrame(animate)
  }

  animate()

  return () => {
    cancelAnimationFrame(animId)
    window.removeEventListener('resize', resize)
  }
}

// ── Component ─────────────────────────────────────────────────────────

export default function Landing() {
  const navigate = useNavigate()
  const landingCanvasRef = useRef<HTMLCanvasElement>(null)
  const mainCanvasRef = useRef<HTMLCanvasElement>(null)
  const landingRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [exiting, setExiting] = useState(false)

  const enterLab = useCallback(() => {
    bodyRef.current?.classList.add('view-active')
    setTimeout(() => {
      if (landingRef.current) landingRef.current.style.display = 'none'
    }, 1000)
  }, [])

  // Smooth exit: fade-out + slide-up, then navigate
  const navigateOut = useCallback((path: string) => {
    if (exiting) return
    setExiting(true)
    setTimeout(() => navigate(path), 700)
  }, [exiting, navigate])

  useEffect(() => {
    const cleanups: (() => void)[] = []
    if (landingCanvasRef.current) {
      cleanups.push(initNetwork(landingCanvasRef.current, 1.4, 0.5))
    }
    if (mainCanvasRef.current) {
      cleanups.push(initNetwork(mainCanvasRef.current, 0.8, 0.75))
    }
    return () => cleanups.forEach(fn => fn())
  }, [])

  return (
    <div ref={bodyRef} className={`landing-root${exiting ? ' exiting' : ''}`}>
      {/* ── Inline styles (scoped to this page) ── */}
      <style>{`
        .landing-root {
          --bg-color: #ffffff;
          --text-color: #000000;
          --font-main: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          font-family: var(--font-main);
          color: var(--text-color);
          background: var(--bg-color);
          width: 100vw;
          height: 100vh;
          overflow: hidden;
          position: relative;
        }

        .landing-view {
          position: fixed;
          top: 0; left: 0;
          width: 100%; height: 100%;
          z-index: 100;
          background: #fff;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 3rem;
          transition: transform 1s cubic-bezier(0.85, 0, 0.15, 1);
        }

        .lab-view {
          position: absolute;
          top: 0; left: 0;
          width: 100%; height: 100%;
          overflow-y: auto;
          opacity: 0;
          visibility: hidden;
          transition: opacity 1s ease;
        }

        .view-active .landing-view { transform: translateY(-100%); }
        .view-active .lab-view { opacity: 1; visibility: visible; }

        .landing-canvas {
          position: absolute;
          top: 0; left: 0;
          width: 100%; height: 100%;
          z-index: -1;
        }

        .nav-minimal {
          display: flex;
          justify-content: space-between;
          text-transform: uppercase;
          font-size: 0.8rem;
          letter-spacing: 0.1em;
          z-index: 10;
        }

        .mission-overlay {
          max-width: 620px;
          z-index: 10;
        }
        .mission-overlay h2 {
          font-size: 4rem;
          line-height: 0.85;
          text-transform: uppercase;
          font-weight: 500;
          margin-bottom: 2rem;
          letter-spacing: -0.02em;
        }
        .mission-overlay p {
          font-size: 1.1rem;
          text-transform: uppercase;
          max-width: 42ch;
          line-height: 1.4;
        }

        .enter-container {
          display: flex;
          justify-content: flex-end;
          z-index: 10;
        }
        .enter-btn {
          font-size: 8vw;
          text-transform: uppercase;
          font-weight: 500;
          line-height: 0.8;
          cursor: pointer;
          border: none;
          background: none;
          text-align: right;
          transition: opacity 0.3s;
          color: inherit;
        }
        .enter-btn:hover { opacity: 0.5; }
        .enter-btn span {
          display: block;
          font-size: 1rem;
          font-weight: 400;
          margin-bottom: 0.5rem;
        }

        /* ── Lab view ── */
        .lab-main {
          padding: 2rem;
          max-width: 1600px;
          margin: 0 auto;
          position: relative;
        }
        .hero { margin-bottom: 15vh; position: relative; }
        .hero-title {
          font-size: 12vw;
          font-weight: 500;
          line-height: 0.9;
          letter-spacing: -0.04em;
          text-transform: uppercase;
        }
        .hero-meta {
          margin-top: 2rem;
          font-size: 1.5rem;
          display: flex;
          gap: 2rem;
          text-transform: uppercase;
        }

        .main-canvas {
          position: fixed;
          top: 0; right: 0;
          width: 50vw; height: 100vh;
          z-index: 1;
          pointer-events: none;
        }

        .services-section {
          display: grid;
          grid-template-columns: 1fr 2fr;
          gap: 4rem;
          margin-bottom: 10vh;
        }
        .section-label {
          font-size: 3rem;
          line-height: 0.9;
          text-transform: uppercase;
          position: sticky;
          top: 2rem;
        }
        .service-list { list-style: none; padding: 0; margin: 0; }
        .service-item {
          margin-bottom: 4rem;
          display: grid;
          grid-template-columns: 80px 1fr;
        }
        .service-content h3 {
          font-size: 1.1rem;
          font-weight: 400;
          text-transform: uppercase;
          font-style: italic;
          margin-bottom: 0.5rem;
        }
        .service-content p {
          font-size: 1.1rem;
          text-transform: uppercase;
          margin-bottom: 1rem;
          max-width: 40ch;
        }
        .feature-list { list-style: none; margin-top: 1rem; padding: 0; }
        .feature-list li {
          position: relative;
          padding-left: 1.5rem;
          margin-bottom: 0.25rem;
          text-transform: uppercase;
        }
        .feature-list li::before {
          content: '+';
          position: absolute;
          left: 0;
        }

        .landing-footer { margin-top: 20vh; padding-bottom: 5rem; }
        .footer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
        .legal-block {
          font-size: 0.85rem;
          text-transform: uppercase;
          max-width: 60ch;
        }
        .cta-btn {
          font-size: 3rem;
          text-transform: uppercase;
          text-decoration: none;
          color: #000;
          border: none;
          background: none;
          cursor: pointer;
          transition: opacity 0.3s;
        }
        .cta-btn:hover { opacity: 0.5; }

        /* ── Exit transition ── */
        .landing-root.exiting {
          animation: labExit 0.7s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }
        @keyframes labExit {
          0%   { opacity: 1; transform: translateY(0) scale(1); }
          100% { opacity: 0; transform: translateY(-40px) scale(0.98); }
        }

        /* ── Lab nav ── */
        .lab-nav {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1.5rem 2rem;
          text-transform: uppercase;
          font-size: 0.8rem;
          letter-spacing: 0.1em;
          position: sticky;
          top: 0;
          z-index: 50;
          background: rgba(255,255,255,0.85);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
        }
        .lab-nav-brand { font-weight: 600; cursor: pointer; }
        .lab-nav-links { display: flex; gap: 2rem; }
        .lab-nav-link {
          cursor: pointer;
          border: none;
          background: none;
          font-family: inherit;
          font-size: inherit;
          letter-spacing: inherit;
          text-transform: inherit;
          color: inherit;
          transition: opacity 0.2s;
          padding: 0;
        }
        .lab-nav-link:hover { opacity: 0.5; }

        @media (max-width: 768px) {
          .services-section { grid-template-columns: 1fr; }
          .hero-title { font-size: 18vw; }
          .mission-overlay h2 { font-size: 2.5rem; }
          .footer-grid { grid-template-columns: 1fr; }
        }
      `}</style>

      {/* ═══════════════════  LANDING VIEW  ═══════════════════ */}
      <section className="landing-view" ref={landingRef}>
        <canvas className="landing-canvas" ref={landingCanvasRef} />

        <nav className="nav-minimal">
          <div>IDEALAB // v1.0</div>
          <div>STATUS: READY</div>
          <div>SYNTHETIC POPULATION ENGINE</div>
        </nav>

        <div className="mission-overlay">
          <h2>
            TEST YOUR
            <br />
            IDEAS BEFORE
            <br />
            YOU BUILD
          </h2>
          <p>
            INJECT A PRODUCT IDEA INTO A SIMULATED SOCIETY OF AI-DRIVEN
            PERSONAS AND GET STRUCTURED MARKET SIGNAL &mdash; IN MINUTES, NOT
            WEEKS.
          </p>
        </div>

        <div className="enter-container">
          <button className="enter-btn" onClick={enterLab}>
            <span>ACCESS SIMULATION</span>
            ENTER LAB &mdash;
          </button>
        </div>
      </section>

      {/* ═══════════════════  LAB VIEW  ═══════════════════ */}
      <section className="lab-view">
        <canvas className="main-canvas" ref={mainCanvasRef} />

        <nav className="lab-nav">
          <div className="lab-nav-brand">IDEALAB</div>
          <div className="lab-nav-links">
            <button className="lab-nav-link" onClick={() => navigateOut('/dashboard')}>
              Dashboard
            </button>
            <button className="lab-nav-link" onClick={() => navigateOut('/inject')}>
              New Simulation
            </button>
          </div>
        </nav>

        <main className="lab-main">
          <header className="hero">
            <h1 className="hero-title">
              IDEA
              <br />
              LAB &mdash;
            </h1>

            <div className="hero-meta">
              <div>
                SYNTHETIC POPULATION
                <br />
                ENGINE
              </div>
              <div>
                IDEA-TESTING
                <br />
                &amp; SIGNAL BUREAU
              </div>
            </div>
          </header>

          <section className="services-section">
            <div className="section-label">
              CAPABIL
              <br />
              ITIES
            </div>

            <ul className="service-list">
              <li className="service-item">
                <div style={{ fontWeight: 400 }}>01:00</div>
                <div className="service-content">
                  <h3>POPULATION SIMULATION</h3>
                  <p>
                    30+ AI-DRIVEN PERSONAS EVALUATE YOUR IDEA INDIVIDUALLY, THEN
                    DISCUSS WITH CONNECTED PEERS OVER MULTIPLE ROUNDS.
                  </p>
                  <ul className="feature-list">
                    <li>ARCHETYPE-BASED NPC GENERATION</li>
                    <li>SOCIAL GRAPH WITH TRUST DYNAMICS</li>
                    <li>CONVERGENCE &amp; POLARIZATION TRACKING</li>
                  </ul>
                </div>
              </li>
              <li className="service-item">
                <div style={{ fontWeight: 400 }}>02:00</div>
                <div className="service-content">
                  <h3>SIGNAL ANALYSIS</h3>
                  <p>
                    STRUCTURED REPORTS ON ADOPTION LIKELIHOOD, TOP OBJECTIONS,
                    VIRAL POTENTIAL, AND SEGMENT BREAKDOWN.
                  </p>
                  <ul className="feature-list">
                    <li>8-DIMENSION PRODUCT PROFILE</li>
                    <li>SEGMENT-BY-SEGMENT REACTIONS</li>
                    <li>AI-GENERATED RECOMMENDATIONS</li>
                  </ul>
                </div>
              </li>
              <li className="service-item">
                <div style={{ fontWeight: 400 }}>03:00</div>
                <div className="service-content">
                  <h3>REFERENCE ASSETS</h3>
                  <p>
                    UPLOAD SCREENSHOTS, MOCKUPS, OR PROTOTYPES. AI VISION
                    EXTRACTS TRUST, POLISH, AND CLARITY SIGNALS.
                  </p>
                  <ul className="feature-list">
                    <li>7-DIMENSION VISUAL SIGNAL EXTRACTION</li>
                    <li>PER-NPC PERSONALITY-WEIGHTED ADJUSTMENTS</li>
                    <li>PRODUCT PROFILE MODIFICATION</li>
                  </ul>
                </div>
              </li>
              <li className="service-item">
                <div style={{ fontWeight: 400 }}>04:00</div>
                <div className="service-content">
                  <h3>LIVE OBSERVATION</h3>
                  <p>
                    WATCH IDEAS SPREAD THROUGH THE SOCIAL GRAPH IN REAL TIME.
                    CLICK ANY NPC TO INSPECT THEIR REASONING OR CHAT WITH THEM.
                  </p>
                  <ul className="feature-list">
                    <li>FORCE-DIRECTED SOCIAL GRAPH</li>
                    <li>REAL-TIME EVENT FEED</li>
                    <li>GROUNDED NPC CONVERSATIONS</li>
                  </ul>
                </div>
              </li>
            </ul>
          </section>

          <footer className="landing-footer">
            <div className="footer-grid">
              <div>
                <div
                  style={{
                    fontSize: '4rem',
                    lineHeight: 0.8,
                    marginBottom: '2rem',
                    fontWeight: 500,
                    textTransform: 'uppercase',
                  }}
                >
                  READY
                  <br />
                  TO
                  <br />
                  TEST?
                </div>
                <button
                  className="cta-btn"
                  onClick={() => navigateOut('/inject')}
                >
                  LAUNCH SIMULATION &mdash;
                </button>
              </div>
              <div className="legal-block">
                SYNTHETIC POPULATION ENGINE. ALL REACTIONS GENERATED BY
                AI-DRIVEN PERSONAS POWERED BY CLAUDE. RESULTS ARE DIRECTIONAL
                MARKET SIGNALS, NOT GUARANTEES. EACH SIMULATION TARGETS UNDER
                $0.15 IN API COSTS.
              </div>
            </div>
          </footer>
        </main>
      </section>
    </div>
  )
}
