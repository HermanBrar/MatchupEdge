const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export type Game = { id: string; sport: string; home_team: string; away_team: string; starts_at: string; data_mode: string }
export type Projection = { id: string; game_id: string; sport: string; player: string; team: string; market: string; line: number | null; projected: number; over_probability: number | null; under_probability: number | null; data_mode?: string; generated_at?: string; predictive_lower?: number; predictive_upper?: number; sample_size?: number; data_quality?: string }
export type Status = { mode: string; label: string; live_configured: boolean; note: string }

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`API request failed: ${response.status}`)
  return response.json()
}

export const api = {
  demo: (sport: string) => get<{status: Status; games: Game[]; projections: Projection[]}>(`/api/v1/demo?sport=${sport}`),
  status: () => get<Status>('/api/v1/status'),
  games: (sport: string) => get<Game[]>(`/api/v1/games?sport=${sport}`),
  projections: (sport: string, real: boolean) => get<Projection[]>(real ? `/api/v1/real/projections?sport=${sport}` : `/api/v1/projections?sport=${sport}`),
  evaluateParlay: (legs: unknown[], stake: number) => fetch(`${API_URL}/api/v1/parlays/evaluate`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ legs, stake }) }).then((response) => response.json()),
}

export type Quote = { sportsbook: string; sportsbook_key: string; line: number | null; period: string; quote_timestamp: string; retrieved_at: string; stale: boolean; odds: Record<string, number>; probabilities: Record<string, number | null> | null; ev: Record<string, number> | null; rules: string; rules_source?: string | null }
export type Forecast = { available: boolean; reason?: string; projected?: number; predictive_lower?: number; predictive_upper?: number; td_probability?: number; td_rules?: { description: string; source: string }; sample_size: number; model_version?: string; feature_cutoff?: string; last_input_game?: string; source_retrieved_at?: string; inputs?: Record<string, number>; validation?: Record<string, string | number>; factors?: string[]; uncertainties?: string[] }
export type WeeklyGame = { id: string; sport: string; season: number; season_type: string; week: number | null; home_team: string; away_team: string; starts_at: string | null; status: string; source: string; retrieved_at: string }
export type PlayerGroup = { player_id: string; player: string; team: string; opponent: string; game_id: string; roster_status: string; roster_season: number; roster_week: number; roster_retrieved_at: string; markets: { market: string; forecast: Forecast; quotes: Quote[]; line_status: string }[] }
export type Slate = { selection: { sport: string; season: number; season_type: string; week: number | null; date: string | null; view: string }; games: WeeklyGame[]; players: PlayerGroup[]; seasons: number[]; slates: [number, string, number][]; sportsbooks: {key: string; title: string}[]; messages: string[]; excluded_players: { player: string; reason: string }[]; as_of: string; mode: string; snapshots?: { game: WeeklyGame; created_at: string; players: PlayerGroup[] }[] }
export async function slateRequest<T>(path: string, query: string, method = 'GET', signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}/api/v1/${path}?${query}`, { method, signal })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `API request failed: ${response.status}`)
  }
  return response.json()
}
