import { useState, useEffect } from 'react'

function App() {
  const [status, setStatus] = useState<string>('Yükleniyor...')

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/status`)
      .then((response) => response.json())
      .then((data) => setStatus(JSON.stringify(data, null, 2)))
      .catch((error) => setStatus('Hata: ' + error.message))
  }, [])

  return (
    <div style={{ padding: '2rem', fontFamily: 'monospace' }}>
      <h1>Weather Service — Bağlantı Testi</h1>
      <pre>{status}</pre>
    </div>
  )
}

export default App