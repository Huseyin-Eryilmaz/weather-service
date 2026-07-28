import type { Location } from '../types'

function LocationCard({
  location,
  onSelect,
  isSelected,
}: {
  location: Location
  onSelect: (id: number) => void
  isSelected: boolean
}) {
  return (
    <li
      className={isSelected ? 'location-card selected' : 'location-card'}
      onClick={() => onSelect(location.id)}
    >
      <span className="location-name">{location.name}</span>{' '}
      <span className="location-coords">
        {location.latitude.toFixed(2)}, {location.longitude.toFixed(2)}
      </span>
    </li>
  )
}

export default LocationCard