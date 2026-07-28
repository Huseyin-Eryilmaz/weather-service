import './App.css'
import { useState, useEffect } from 'react'
import LocationCard from './components/LocationCard'
import type { Location, Weather } from './types'

function App() {
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState<string>('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [weather, setWeather] = useState<Weather | null>(null)
  const [weatherLoading, setWeatherLoading] = useState<boolean>(false)
  const [weatherError, setWeatherError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/locations`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Sunucu ${response.status} döndü`)
        }
        return response.json()
      })
      .then((data: Location[]) => {
        setLocations(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (selectedId === null) {
      return
    }

    let cancelled = false

    const loadWeather = async () => {
      setWeatherLoading(true)
      setWeatherError(null)
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/locations/${selectedId}/current`,
        )
        if (!response.ok) {
          throw new Error(`Sunucu ${response.status} döndü`)
        }
        const data: Weather = await response.json()
        if (!cancelled) {
          setWeather(data)
        }
      } catch (err) {
        if (!cancelled) {
          setWeatherError(err instanceof Error ? err.message : 'Bilinmeyen hata')
        }
      } finally {
        if (!cancelled) {
          setWeatherLoading(false)
        }
      }
    }

    loadWeather()

    return () => {
      cancelled = true
    }
  }, [selectedId])

  if (loading) {
    return <p style={{ padding: '2rem' }}>Yükleniyor...</p>
  }

  if (error) {
    return <p style={{ padding: '2rem', color: 'red' }}>Hata: {error}</p>
  }

  const filteredLocations = locations.filter((location) =>
    location.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
  <div className="container">
    <h1 className="title">Konumlar ({filteredLocations.length})</h1>

    {selectedId && (
      <div className="weather-panel">
        {weatherLoading && <p>Hava durumu yükleniyor...</p>}
        {weatherError && <p style={{ color: 'red' }}>Hata: {weatherError}</p>}
        {weather && (
          <div className="weather-stats">
            <div>
              <div className="weather-stat-label">Sıcaklık</div>
              <div className="weather-stat-value">{weather.temperature_c}°C</div>
            </div>
            <div>
              <div className="weather-stat-label">Nem</div>
              <div className="weather-stat-value">{weather.humidity_pct}%</div>
            </div>
            <div>
              <div className="weather-stat-label">Rüzgar</div>
              <div className="weather-stat-value">{weather.wind_speed_kmh} km/s</div>
            </div>
          </div>
        )}
      </div>
    )}

    <input
      type="text"
      className="search-box"
      placeholder="Şehir ara..."
      value={search}
      onChange={(e) => setSearch(e.target.value)}
    />

    <ul className="location-list">
      {filteredLocations.map((location) => (
        <LocationCard
          key={location.id}
          location={location}
          onSelect={setSelectedId}
          isSelected={location.id === selectedId}
        />
      ))}
    </ul>
  </div>
)}

export default App