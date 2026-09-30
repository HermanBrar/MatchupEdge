import { useEffect, useMemo, useState } from 'react'
import { Activity, ArrowUpRight, BarChart3, CircleAlert, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import { api, Game, Projection, Status } from './api'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

function App() {
  const [sport, setSport] = useState('NFL')
  const [status, setStatus] = useState<Status | null>(null)
  const [games, setGames] = useState<Game[]>([])
  const [projections, setProjections] = useState<Projection[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [stake, setStake] = useState(10)
  const [parlay, setParlay] = useState<{valid?: boolean; message?: string; joint_probability?: number; potential_profit?: number; expected_return?: number; correlation_status?: string} | null>(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      setError('')
      const { status: nextStatus, games: nextGames, projections: nextProjections } = await api.demo(sport)
      setStatus(nextStatus); setGames(nextGames); setProjections(nextProjections); setSelected([]); setParlay(null)
    } catch { setError('The API is unavailable. Start the FastAPI service and refresh.') }
  }
  useEffect(() => { void load() }, [sport])

  const selectedLegs = useMemo(() => projections.filter((projection) => selected.includes(projection.id)), [projections, selected])
  const toggleLeg = (projection: Projection) => setSelected((current) => current.includes(projection.id) ? current.filter((id) => id !== projection.id) : current.length < 4 ? [...current, projection.id] : current)
  async function evaluate() {
    const legs = selectedLegs.map((projection) => ({ id: projection.id, game_id: projection.game_id, label: `${projection.player} ${projection.market} over ${projection.line}`, probability: projection.over_probability, decimal_odds: 1.91 }))
    setParlay(await api.evaluateParlay(legs, stake))
  }

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-mark"><Activity size={20} /></div><div><strong>Matchup<span>Edge</span></strong><small>projection desk / v0.1</small></div></div><div className="top-actions"><button className="icon-button" title="Refresh data" onClick={() => void load()}><RefreshCw size={18} /></button><div className="mode-pill"><span />{status?.label || 'Connecting'}</div></div></header>
    <main className="content">
      <section className="intro"><div><p className="eyebrow">Decision support, without the certainty theater</p><h1>Read the matchup<br /><em>before the market does.</em></h1><p className="lede">Transparent player baselines, price-aware math, and a parlay workspace built to show its assumptions.</p></div><div className="intro-note"><ShieldCheck size={18} /><div><strong>Data boundary</strong><p>{status?.note || 'Loading data provenance...'}</p></div></div></section>
      {error && <div className="error"><CircleAlert size={18} />{error}</div>}
      <section className="toolbar"><div className="tabs">{['NFL', 'NBA'].map((item) => <button key={item} className={sport === item ? 'tab active' : 'tab'} onClick={() => setSport(item)}>{item}</button>)}</div><div className="toolbar-meta"><span>America/Indianapolis</span><button className="refresh" onClick={() => void load()}><RefreshCw size={15} /> Refresh</button></div></section>
      <section className="metrics"><div className="metric"><span>UPCOMING SLATE</span><strong>{games.length.toString().padStart(2, '0')}</strong><small>{status?.mode === 'demo' ? 'games in demo feed' : 'real provider games'}</small></div><div className="metric"><span>SUPPORTED MARKETS</span><strong>{projections.length.toString().padStart(2, '0')}</strong><small>{status?.mode === 'demo' ? 'demo baselines' : 'real baseline projections'}</small></div><div className="metric accent"><span>WORKSPACE</span><strong>{selected.length}/4</strong><small>parlay legs selected</small></div></section>
      <section className="workspace"><div className="panel projections-panel"><div className="panel-heading"><div><p className="eyebrow">Market board</p><h2>{sport} player projections</h2></div><span className="badge">{status?.mode === 'demo' ? 'BASELINE / DEMO' : 'REAL DATA / BASELINE'}</span></div><div className="table-wrap"><table><thead><tr><th>Player</th><th>Matchup</th><th>Market</th><th>Model</th><th>Over</th><th></th></tr></thead><tbody>{projections.map((projection) => { const game = games.find((item) => item.id === projection.game_id); const active = selected.includes(projection.id); return <tr key={projection.id} className={active ? 'selected-row' : ''}><td><strong>{projection.player}</strong><small>{projection.team}</small></td><td><span className="matchup">{game?.away_team} <b>@</b> {game?.home_team}</span></td><td>{projection.market}<small>{projection.line === null ? 'no sportsbook line' : `line ${projection.line}`}</small></td><td><strong>{projection.projected.toFixed(1)}</strong><small>{projection.predictive_lower === undefined ? 'interval pending' : `${projection.predictive_lower.toFixed(1)} - ${projection.predictive_upper?.toFixed(1)}`}</small></td><td><span className={projection.over_probability !== null && projection.over_probability >= .5 ? 'prob positive' : 'prob'}>{projection.over_probability === null ? 'N/A' : `${Math.round(projection.over_probability * 100)}%`}</span><small>{projection.over_probability === null ? 'line unavailable' : 'over estimate'}</small></td><td><button className={active ? 'select selected' : 'select'} onClick={() => toggleLeg(projection)}>{active ? 'Added' : 'Add leg'}<ArrowUpRight size={14} /></button></td></tr>})}</tbody></table></div></div>
        <aside className="panel parlay-panel"><div className="panel-heading"><div><p className="eyebrow">Manual evaluator</p><h2>Parlay workspace</h2></div><Sparkles size={18} className="spark" /></div><p className="panel-copy">Select different-game legs to see an independent-product estimate. Same-game correlation is intentionally unavailable until a validated joint model exists.</p><div className="leg-list">{selectedLegs.length === 0 ? <div className="empty">Choose two to four legs from the board.</div> : selectedLegs.map((leg) => <div className="leg" key={leg.id}><div><strong>{leg.player}</strong><span>{leg.market} over {leg.line}</span></div><button onClick={() => toggleLeg(leg)}>×</button></div>)}</div><label className="field">Stake<input type="number" min="1" value={stake} onChange={(event) => setStake(Number(event.target.value))} /></label><button className="evaluate" disabled={selectedLegs.length < 2} onClick={() => void evaluate()}>Evaluate parlay <ArrowUpRight size={16} /></button>{parlay && <div className={parlay.valid ? 'result' : 'result invalid'}><div><span>EST. HIT PROBABILITY</span><strong>{parlay.joint_probability ? `${Math.round(parlay.joint_probability * 100)}%` : 'Unavailable'}</strong></div>{parlay.valid && <div><span>EXPECTED RETURN</span><strong>{money.format(parlay.expected_return || 0)}</strong></div>}<p>{parlay.message}</p></div>}</aside></section>
      <footer><BarChart3 size={16} /><span>{status?.mode === 'demo' ? 'Demo mode uses deterministic synthetic fixtures.' : 'Real mode uses provider records and transparent baseline models.'} No accuracy or profitability claim is made.</span><span className="footer-right">Model v0.2 · provenance visible</span></footer>
    </main>
  </div>
}

export default App
