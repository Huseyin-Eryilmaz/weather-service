import type { Location } from '../types'

function LocationCard({
  location,
  onSelect,
}: {
  location: Location
  onSelect: (id: number) => void
}) {
  return (
    <li
      onClick={() => onSelect(location.id)}
      style={{ cursor: 'pointer' }}
    >
      {location.name} — {location.latitude.toFixed(2)},{' '}
      {location.longitude.toFixed(2)}
    </li>
  )
}

export default LocationCard