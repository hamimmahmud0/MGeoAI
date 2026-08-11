declare namespace GeoJSON {
  type Position = number[]
  interface Point { type: 'Point'; coordinates: [number, number] }
  interface Polygon { type: 'Polygon'; coordinates: Position[][] }
  interface Feature<G = Point> { type: 'Feature'; id?: string | number; geometry: G; properties: Record<string, unknown> | null }
  interface FeatureCollection<G = Point> { type: 'FeatureCollection'; features: Feature<G>[] }
}
