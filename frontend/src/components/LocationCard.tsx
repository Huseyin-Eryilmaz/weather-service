import type { Location } from '../types'

function LocationCard({ location }: { location: Location }) {
  return (
    <li>
      {location.name} — {location.latitude.toFixed(2)},{' '}
      {location.longitude.toFixed(2)}
    </li>
  )
}

export default LocationCard