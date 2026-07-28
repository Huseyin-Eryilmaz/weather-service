import { useState, useEffect } from 'react'
import type { Location } from './types'
import LocationCard from './components/LocationCard'

function App() {
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

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

  if (loading) {
    return <p style={{ padding: '2rem' }}>Yükleniyor...</p>
  }

  if (error) {
    return <p style={{ padding: '2rem', color: 'red' }}>Hata: {error}</p>
  }

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>Konumlar ({locations.length})</h1>
      <ul>
        {locations.map((location) => (
          <LocationCard key={location.id} location={location} />
        ))}
      </ul>
    </div>
  )
}

export default App