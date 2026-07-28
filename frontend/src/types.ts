export interface Location {
  id: number
  name: string
  latitude: number
  longitude: number
  country: string
  is_active: boolean
  created_at: string
}

export interface Weather {
  observed_at: string
  temperature_c: number
  humidity_pct: number
  wind_speed_kmh: number
  precipitation_mm: number
  weather_code: number | null
}