// WMO weather interpretation codes -> Turkish label + emoji.
// Ref: Open-Meteo / WMO code table. Grouped by range for brevity;
// each range shares a description.
export function describeWeather(code: number | null): string {
  if (code === null) {
    return 'Bilinmiyor'
  }
  const map: Record<number, string> = {
    0: '☀️ Açık',
    1: '🌤️ Az bulutlu',
    2: '⛅ Parçalı bulutlu',
    3: '☁️ Kapalı',
    45: '🌫️ Sisli',
    48: '🌫️ Kırağılı sis',
    51: '🌦️ Hafif çisenti',
    53: '🌦️ Çisenti',
    55: '🌦️ Yoğun çisenti',
    61: '🌧️ Hafif yağmur',
    63: '🌧️ Yağmur',
    65: '🌧️ Kuvvetli yağmur',
    71: '🌨️ Hafif kar',
    73: '🌨️ Kar',
    75: '🌨️ Yoğun kar',
    80: '🌦️ Sağanak',
    81: '🌧️ Kuvvetli sağanak',
    82: '⛈️ Şiddetli sağanak',
    95: '⛈️ Gök gürültülü fırtına',
    96: '⛈️ Dolulu fırtına',
    99: '⛈️ Şiddetli dolulu fırtına',
  }
  return map[code] ?? `Kod ${code}`
}