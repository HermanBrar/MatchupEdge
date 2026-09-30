import { useEffect, useState } from 'react'
import { Activity, RefreshCw } from 'lucide-react'
import { api, slateRequest, Slate, PlayerGroup, WeeklyGame, Quote } from './api'
import DemoApp from './DemoApp'

const pct = (n: number | null | undefined) => n == null ? 'Unavailable' : `${(n * 100).toFixed(1)}%`
const when = (s: string | null | undefined) => s ? new Date(s.endsWith('Z') || /[+-]\d\d:\d\d$/.test(s) ? s : `${s}Z`).toLocaleString('en-US', { timeZone: 'America/Indiana/Indianapolis', dateStyle: 'medium', timeStyle: 'short' }) : 'TBD'
const odds = (n: number) => n > 0 ? `+${n}` : `${n}`

function QuoteRow({ quote }: { quote: Quote }) {
  return <div className="quote-row"><strong>{quote.sportsbook}</strong><span>{quote.line == null ? 'Anytime scorer' : `Line ${quote.line}`} / {quote.period.replace('_', ' ')}</span>
    <span>{Object.entries(quote.odds).map(([side, price]) => `${side} ${odds(price)}`).join(' | ')}</span>
    <span>{quote.probabilities ? Object.entries(quote.probabilities).map(([side, p]) => `${side} ${pct(p)}`).join(' / ') : 'Probabilities unavailable'}</span>
    <span>{quote.ev ? Object.entries(quote.ev).map(([side, ev]) => `${side} EV ${ev >= 0 ? '+' : ''}${(ev * 100).toFixed(1)}% / stake`).join(' | ') : 'EV unavailable'}</span>
    <small>{quote.rules_source && <a href={quote.rules_source} target="_blank" rel="noreferrer">Market rules / </a>}Quote {when(quote.quote_timestamp)}{quote.stale ? ' - STALE; EV withheld' : ''}</small></div>
}

function PlayerCard({ player, game }: { player: PlayerGroup; game: WeeklyGame }) {
  return <article className="panel player-card"><div className="panel-heading"><div><h2>{player.player} <span className="badge">{player.team}</span></h2>
    <p>{game.away_team} @ {game.home_team} / {when(game.starts_at)} ET</p><small>{game.season} {game.season_type}{game.week ? ` / Week ${game.week}` : ''} / Opponent {player.opponent}</small></div></div>
    <details className="identity"><summary>Verified roster identity and freshness</summary><p>{player.player_id}<br />Status {player.roster_status}; roster season {player.roster_season}, week {player.roster_week}; retrieved {when(player.roster_retrieved_at)}<br />Schedule: {game.source}; retrieved {when(game.retrieved_at)}</p></details>
    {player.markets.map(({ market, forecast: f, quotes, line_status }) => <section className="market-section" key={market}><div className="market-title"><h3>{market}</h3><div><strong>{!f.available ? 'Unavailable' : market === 'Anytime touchdown' ? pct(f.td_probability) : f.projected?.toFixed(1)}</strong><small>{!f.available ? f.reason : market === 'Anytime touchdown' ? 'At least one offensive/special-teams TD (FanDuel IN rules)' : `80% predictive range ${f.predictive_lower?.toFixed(0)} - ${f.predictive_upper?.toFixed(0)}`}</small></div></div>
      {quotes.length ? <div className="quote-list">{[...quotes].sort((a, b) => (a.line ?? 0) - (b.line ?? 0) || a.sportsbook.localeCompare(b.sportsbook)).map(q => <QuoteRow key={`${q.sportsbook_key}:${q.line}:${q.period}`} quote={q} />)}</div> : <p className="line-missing">{line_status}</p>}
      {f.available && <details><summary>Matchup inputs, uncertainty and model validation</summary><ul>{f.factors?.map(x => <li key={x}>{x}</li>)}</ul><ul>{f.uncertainties?.map(x => <li key={x}>{x}</li>)}</ul>
        {f.td_rules && <p>{f.td_rules.description} <a href={f.td_rules.source} target="_blank" rel="noreferrer">Rules source</a></p>}<p>Cutoff {when(f.feature_cutoff)} ET; latest input game {when(f.last_input_game)} ET; {f.sample_size} recent games.<br />Statistics retrieved {when(f.source_retrieved_at)} ET. Model {f.model_version}</p>
        <dl className="input-grid">{Object.entries(f.inputs || {}).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value.toFixed(3)}</dd></div>)}</dl>
        <p>Chronological evaluation: {JSON.stringify(f.validation)}</p>{quotes[0] && <p>{quotes[0].rules}</p>}</details>}
    </section>)}
  </article>
}

function App() {
  const [demo, setDemo] = useState(false)
  const [sport, setSport] = useState('NFL')
  const [season, setSeason] = useState('')
  const [type, setType] = useState('')
  const [week, setWeek] = useState('')
  const [date, setDate] = useState('')
  const [view, setView] = useState('upcoming')
  const [book, setBook] = useState('')
  const [search, setSearch] = useState('')
  const [board, setBoard] = useState<Slate | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const query = new URLSearchParams({ sport, view, ...(season ? { season } : {}), ...(type ? { season_type: type } : {}), ...(week ? { week } : {}), ...(date ? { date } : {}) }).toString()
  useEffect(() => { void api.status().then(s => { setDemo(s.mode === 'demo'); if (s.mode === 'historical') setView('history') }).catch(() => {}) }, [])
  useEffect(() => {
    const abort = new AbortController()
    setBoard(null); setError(''); setBusy(true)
    slateRequest<Slate>('slate', query, 'GET', abort.signal).then(setBoard).catch(e => { if (!abort.signal.aborted) setError(e.message) }).finally(() => { if (!abort.signal.aborted) setBusy(false) })
    return () => abort.abort()
  }, [query, revision])
  async function action(path: string) {
    setBusy(true); setError(''); setNotice('')
    try { const result = await slateRequest<Record<string, unknown>>(path, query, 'POST'); setNotice(JSON.stringify(result)); setRevision(n => n + 1) }
    catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); setBusy(false) }
  }
  if (demo) return <><div className="demo-switch"><button onClick={() => setDemo(false)}>Open real weekly slate</button></div><DemoApp /></>
  const selectedSeason = season || String(board?.selection.season || new Date().getFullYear())
  const selectedType = type || board?.selection.season_type || 'REG'
  const weeks = [...new Set(board?.slates.filter(([s, t]) => s === Number(selectedSeason) && t === selectedType).map(([, , w]) => w) || [])]
  const visible = board?.players.filter(p => `${p.player} ${p.team}`.toLowerCase().includes(search.toLowerCase())) || []
  return <div className="app-shell"><header className="topbar"><div className="brand"><div className="brand-mark"><Activity size={20} /></div><strong>Matchup<span>Edge</span></strong></div><div className="mode-pill">{view === 'upcoming' ? 'Live / upcoming' : 'Historical / schedule'}</div></header>
    <main className="content"><section className="intro"><div><p className="eyebrow">One slate. Verified identities. Posted prices.</p><h1>Read the matchup.</h1><p className="lede">Pregame projections with chronological validation and visible missing context.</p></div></section>
      <section className="toolbar slate-controls"><label>Sport<select aria-label="Sport" value={sport} onChange={e => { setSport(e.target.value); setSeason(''); setWeek(''); setType(''); setDate(''); setBook('') }}><option>NFL</option><option>NBA</option></select></label>
        {sport === 'NFL' ? <><label>Season<select aria-label="Season" value={selectedSeason} onChange={e => { setSeason(e.target.value); setWeek(''); setType('') }}>{(board?.seasons || [Number(selectedSeason)]).map(s => <option key={s}>{s}</option>)}</select></label>
          <label>Season type<select aria-label="Season type" value={selectedType} onChange={e => { setType(e.target.value); setWeek('') }}><option value="REG">Regular season</option><option value="PRE">Preseason</option><option value="POST">Postseason</option></select></label>
          <label>Week<select aria-label="Week" value={week || board?.selection.week || ''} onChange={e => setWeek(e.target.value)}><option value="">Next upcoming slate</option>{weeks.map(w => <option key={w} value={w}>Week {w}</option>)}</select></label></> : <label>Slate date (Eastern)<input aria-label="Slate date (Eastern)" type="date" value={date || board?.selection.date || ''} onChange={e => setDate(e.target.value)} /></label>}
        <label>View<select aria-label="View" value={view} onChange={e => setView(e.target.value)}><option value="upcoming">Upcoming games</option><option value="completed">Completed / saved predictions</option><option value="all">Full selected schedule / postponed</option><option value="history">Historical prediction snapshots</option></select></label>
        <label>Sportsbook<select aria-label="Sportsbook" value={book} onChange={e => setBook(e.target.value)}><option value="">Compare all books</option>{board?.sportsbooks.map(b => <option key={b.key} value={b.key}>{b.title}</option>)}</select></label>
        <label>Find a player<input placeholder="Player or team" value={search} onChange={e => setSearch(e.target.value)} /></label>
      </section>
      <div className="slate-actions"><button disabled={busy} onClick={() => setRevision(n => n + 1)}><RefreshCw size={14} /> Reload board</button><button disabled={busy} onClick={() => void action('data/refresh')}>Refresh schedules and statistics</button><button disabled={busy || view !== 'upcoming'} onClick={() => void action('slate/quotes/refresh')}>Fetch sportsbook lines</button><button disabled={busy || view !== 'upcoming'} onClick={() => void action('slate/snapshot')}>Save pregame snapshot</button><button onClick={() => setDemo(true)}>Demo fixtures</button></div>
      {error && <div className="error" role="alert">{error}</div>}{notice && <p role="status">{notice}</p>}{busy && <p role="status">Loading slate...</p>}
      {board && <><div className="slate-summary"><strong>{sport === 'NFL' ? `${board.selection.season} ${selectedType} / Week ${board.selection.week ?? 'not yet scheduled'}` : board.selection.date}</strong><span>{board.games.length} games / {board.players.length} players / as of {when(board.as_of)} ET</span></div>
        <div className="data-notes">{board.messages.map(m => <p key={m}>{m}</p>)}</div>
        <details><summary>Selected schedule and source freshness</summary>{board.games.map(g => <p key={g.id}>{g.away_team} @ {g.home_team} / {when(g.starts_at)} ET / {g.status} / {g.source} retrieved {when(g.retrieved_at)}</p>)}</details>
        {visible.map(p => <PlayerCard key={`${p.player_id}:${p.game_id}`} player={{...p, markets: p.markets.map(m => ({...m, quotes: m.quotes.filter(q => !book || q.sportsbook_key === book), line_status: book && m.quotes.length && !m.quotes.some(q => q.sportsbook_key === book) ? 'Line not posted' : m.line_status }))}} game={board.games.find(g => g.id === p.game_id)!} />)}
        {!busy && visible.length === 0 && <p className="empty">No player forecasts for this selection. {view !== 'upcoming' ? 'Saved pregame predictions appear below when available.' : 'Check the schedule and coverage notes above.'}</p>}
        {board.snapshots?.map((s, i) => <section key={`${s.game.id}:${s.created_at}:${i}`}><h2>Saved {when(s.created_at)} ET</h2>{s.players.map(p => <PlayerCard key={p.player_id} player={p} game={s.game} />)}</section>)}
        {!!board.excluded_players.length && <details><summary>{board.excluded_players.length} players without sufficient inputs</summary>{board.excluded_players.map((p, i) => <p key={i}>{p.player}: {p.reason}</p>)}</details>}
      </>}
      <footer>Source timestamps and model limitations are shown per matchup. No accuracy or profitability claim is made.</footer>
    </main></div>
}
export default App
