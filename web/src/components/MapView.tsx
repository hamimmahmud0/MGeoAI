import { useEffect, useRef } from 'react'
import maplibregl, { type GeoJSONSource, type Map } from 'maplibre-gl'

type Props = {
  data: GeoJSON.FeatureCollection<GeoJSON.Point>
  selectedId?: string
  onSelect: (id: string) => void
  onBounds: (bbox: string) => void
  theme: 'light' | 'dark'
  className?: string
}

const sourceId = 'incidents'
const regionSourceId = 'incident-regions'
const lightStyle = import.meta.env.VITE_MAP_STYLE_LIGHT_URL || import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty'
const darkStyle = import.meta.env.VITE_MAP_STYLE_DARK_URL || 'https://tiles.openfreemap.org/styles/dark'

function regionData(data: GeoJSON.FeatureCollection<GeoJSON.Point>): GeoJSON.FeatureCollection<GeoJSON.Polygon> {
  const features = data.features.flatMap((feature) => {
    const radiusKm = Number(feature.properties?.uncertainty_radius_km || 0)
    const granularity = String(feature.properties?.granularity || '')
    if (!radiusKm || !['area', 'city', 'district'].includes(granularity)) return []
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

export function MapView({ data, selectedId, onSelect, onBounds, theme, className = '' }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map>()
  const dataRef = useRef(data)
  const selectedIdRef = useRef(selectedId)
  const themeRef = useRef(theme)
  const appliedThemeRef = useRef(theme)
  const onSelectRef = useRef(onSelect)
  const onBoundsRef = useRef(onBounds)
  dataRef.current = data
  selectedIdRef.current = selectedId
  onSelectRef.current = onSelect
  onBoundsRef.current = onBounds

  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: themeRef.current === 'dark' ? darkStyle : lightStyle,
      center: [0, 18], zoom: 1.15, attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.on('style.load', () => {
      if (map.getSource(sourceId)) return
      map.addSource(regionSourceId, { type: 'geojson', data: regionData(dataRef.current) })
      map.addLayer({ id: 'incident-region-fill', type: 'fill', source: regionSourceId, paint: { 'fill-color': '#1f5eff', 'fill-opacity': themeRef.current === 'dark' ? 0.14 : 0.1 } })
      map.addLayer({ id: 'incident-region-boundary', type: 'line', source: regionSourceId, paint: { 'line-color': '#1f5eff', 'line-opacity': 0.8, 'line-width': 1.5, 'line-dasharray': [3, 2] } })
      map.addLayer({ id: 'incident-region-label', type: 'symbol', source: regionSourceId, layout: { 'text-field': ['get', 'location_name'], 'text-size': 12, 'text-offset': [0, 1.4], 'text-anchor': 'top', 'text-allow-overlap': false }, paint: { 'text-color': themeRef.current === 'dark' ? '#dbe7ff' : '#173b85', 'text-halo-color': themeRef.current === 'dark' ? '#101828' : '#ffffff', 'text-halo-width': 1.5 } })
      map.addSource(sourceId, { type: 'geojson', data: dataRef.current, cluster: true, clusterMaxZoom: 11, clusterRadius: 46 })
      map.addLayer({ id: 'clusters', type: 'circle', source: sourceId, filter: ['has', 'point_count'], paint: { 'circle-color': '#1f5eff', 'circle-radius': ['step', ['get', 'point_count'], 17, 10, 21, 50, 26], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'cluster-count', type: 'symbol', source: sourceId, filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12 }, paint: { 'text-color': '#ffffff' } })
      map.addLayer({ id: 'unclustered', type: 'circle', source: sourceId, filter: ['!', ['has', 'point_count']], paint: {
        'circle-color': ['case', ['==', ['get', 'incident_id'], selectedIdRef.current || ''], '#172033', '#e5484d'],
        'circle-radius': ['case', ['==', ['get', 'granularity'], 'area'], 9, 7],
        'circle-opacity': ['case', ['==', ['get', 'granularity'], 'area'], 0.72, 0.95],
        'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2,
      } })
    })
    map.on('load', () => {
      map.on('click', 'clusters', async (event) => {
        const feature = map.queryRenderedFeatures(event.point, { layers: ['clusters'] })[0]
        const clusterId = Number(feature?.properties?.cluster_id)
        const source = map.getSource(sourceId) as GeoJSONSource
        const zoom = await source.getClusterExpansionZoom(clusterId)
        const point = feature.geometry as unknown as GeoJSON.Point
        map.easeTo({ center: point.coordinates, zoom })
      })
      map.on('click', 'unclustered', (event) => {
        const id = String(event.features?.[0]?.properties?.incident_id || '')
        if (id) onSelectRef.current(id)
      })
      for (const layer of ['clusters', 'unclustered']) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      const bounds = map.getBounds()
      onBoundsRef.current([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map((v) => v.toFixed(4)).join(','))
    })
    map.on('moveend', () => {
      const bounds = map.getBounds()
      onBoundsRef.current([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map((v) => v.toFixed(4)).join(','))
    })
    mapRef.current = map
    return () => { map.remove(); mapRef.current = undefined }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource(sourceId) as GeoJSONSource | undefined
    source?.setData(data as never)
    const regions = mapRef.current?.getSource(regionSourceId) as GeoJSONSource | undefined
    regions?.setData(regionData(data) as never)
  }, [data])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getLayer('unclustered')) return
    map.setPaintProperty('unclustered', 'circle-color', ['case', ['==', ['get', 'incident_id'], selectedId || ''], '#172033', '#e5484d'])
    if (selectedId) {
      const feature = data.features.find((item) => item.properties?.incident_id === selectedId)
      if (feature) map.easeTo({ center: feature.geometry.coordinates, zoom: Math.max(map.getZoom(), 10), duration: 500 })
    }
  }, [selectedId, data])

  useEffect(() => {
    themeRef.current = theme
    const map = mapRef.current
    if (map && appliedThemeRef.current !== theme) {
      appliedThemeRef.current = theme
      map.setStyle(theme === 'dark' ? darkStyle : lightStyle)
    }
  }, [theme])

  return <div ref={container} className={`h-full min-h-[320px] w-full ${className}`} aria-label="Road and region map of traffic incidents" />
}
