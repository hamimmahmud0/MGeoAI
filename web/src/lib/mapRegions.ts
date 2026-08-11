export function regionData(data: GeoJSON.FeatureCollection<GeoJSON.Point>): GeoJSON.FeatureCollection<GeoJSON.Polygon> {
  const features = data.features.flatMap((feature) => {
    const radiusKm = Number(feature.properties?.uncertainty_radius_km || 0)
    if (!radiusKm) return []
    const [longitude, latitude] = feature.geometry.coordinates
    const coordinates: GeoJSON.Position[] = []
    const latitudeDegrees = radiusKm / 111.32
    const longitudeDegrees = radiusKm / (111.32 * Math.max(Math.cos(latitude * Math.PI / 180), 0.2))
    for (let step = 0; step <= 64; step += 1) {
      const angle = step / 64 * Math.PI * 2
      coordinates.push([longitude + Math.cos(angle) * longitudeDegrees, latitude + Math.sin(angle) * latitudeDegrees])
    }
    return [{ type: 'Feature' as const, id: feature.id, properties: feature.properties, geometry: { type: 'Polygon' as const, coordinates: [coordinates] } }]
  })
  return { type: 'FeatureCollection', features }
}
