import { useEffect, useRef } from 'react'
import maplibregl, { type GeoJSONSource, type Map } from 'maplibre-gl'
import { regionData } from '../lib/mapRegions'
import { buildPopup } from '../lib/popup'
import { SEVERITY_STEPS, VEHICLE_COLORS, YEAR_COLORS, type ColorBy } from '../lib/mapStyle'
import { discRadius, spreadDiscs } from '../lib/spread'

type Props = {
  data: GeoJSON.FeatureCollection<GeoJSON.Point>
  selectedId?: string
  colorBy?: ColorBy
  onSelect: (id: string) => void
  onBounds: (bbox: string) => void
  onOpenArticle?: (id: string) => void
  theme: 'light' | 'dark'
  className?: string
}

// Below this zoom nearby incidents are merged into numbered circles; from this zoom up every accident
// is its own circle, pushed apart on screen only as far as needed so that none overlap.
const SPREAD_ZOOM = 6
const sourceId = 'incidents'
const pointsId = 'incident-points'
const leadersId = 'incident-leaders'
const regionSourceId = 'incident-regions'
const lightStyle = import.meta.env.VITE_MAP_STYLE_LIGHT_URL || import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty'
const darkStyle = import.meta.env.VITE_MAP_STYLE_DARK_URL || 'https://tiles.openfreemap.org/styles/dark'
const killed = ['to-number', ['get', 'killed_n'], 0] as never

function pointColor(colorBy: ColorBy, selectedId: string): never {
  let byValue: unknown
  if (colorBy === 'vehicle') byValue = ['match', ['get', 'vehicle_main'], ...VEHICLE_COLORS.slice(0, -1).flatMap(([key, color]) => [key, color]), '#6b7280']
  else if (colorBy === 'year') byValue = ['match', ['to-number', ['get', 'year'], 0], ...YEAR_COLORS.flatMap(([key, color]) => [key, color]), '#6b7280']
  else byValue = ['step', killed, SEVERITY_STEPS[0][1], ...SEVERITY_STEPS.slice(1).flatMap(([from, color]) => [from, color])]
  // amber = collection-country centroid layer (not an incident); the selected marker turns dark
  return ['case', ['==', ['get', 'incident_id'], selectedId], '#111827', ['==', ['get', 'is_incident_location'], false], '#d58a12', byValue] as never
}

export function MapView({ data, selectedId, colorBy = 'severity', onSelect, onBounds, onOpenArticle, theme, className = '' }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map>()
  const dataRef = useRef(data)
  const selectedIdRef = useRef(selectedId)
  const colorRef = useRef(colorBy)
  const themeRef = useRef(theme)
  const appliedThemeRef = useRef(theme)
  const onSelectRef = useRef(onSelect)
  const onBoundsRef = useRef(onBounds)
  const onOpenRef = useRef(onOpenArticle)
  onOpenRef.current = onOpenArticle
  dataRef.current = data
  selectedIdRef.current = selectedId
  colorRef.current = colorBy
  onSelectRef.current = onSelect
  onBoundsRef.current = onBounds

  const spreadRef = useRef<() => void>()
  const selectedRegion = (items: GeoJSON.FeatureCollection<GeoJSON.Point>, id?: string) =>
    regionData({ type: 'FeatureCollection', features: items.features.filter((feature) => id && feature.properties?.incident_id === id) })

  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: themeRef.current === 'dark' ? darkStyle : lightStyle,
      center: [20, 20], zoom: 1.6, attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    // Screen-space layout: incidents that share a place (or are too close) fan out, with a thin line to the true place.
    const spread = () => {
      const points = map.getSource(pointsId) as GeoJSONSource | undefined
      const leaders = map.getSource(leadersId) as GeoJSONSource | undefined
      if (!points || !leaders) return
      const features = dataRef.current.features.filter((feature) => feature.properties?.is_incident_location !== false)
      const projected = features.map((feature) => map.project(feature.geometry.coordinates as [number, number]))
      const moved = spreadDiscs(features.map((feature, i) => ({ x: projected[i].x, y: projected[i].y, r: discRadius(Number(feature.properties?.killed_n ?? 0) || 0) })))
      const lines: { type: 'Feature'; properties: Record<string, never>; geometry: { type: 'LineString'; coordinates: number[][] } }[] = []
      const shown = features.map((feature, i) => {
        const to = map.unproject([moved[i].x, moved[i].y])
        if (Math.hypot(moved[i].x - projected[i].x, moved[i].y - projected[i].y) > 5) {
          lines.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [feature.geometry.coordinates, [to.lng, to.lat]] } })
        }
        return { ...feature, geometry: { type: 'Point' as const, coordinates: [to.lng, to.lat] } }
      })
      points.setData({ type: 'FeatureCollection', features: shown } as never)
      leaders.setData({ type: 'FeatureCollection', features: lines } as never)
    }
    spreadRef.current = spread
    map.on('style.load', () => {
      if (map.getSource(sourceId)) return
      const dark = themeRef.current === 'dark'
      // only the selected incident shows its uncertainty circle: all of them at once would bury the map
      map.addSource(regionSourceId, { type: 'geojson', data: selectedRegion(dataRef.current, selectedIdRef.current) })
      map.addLayer({ id: 'incident-region-fill', type: 'fill', source: regionSourceId, paint: { 'fill-color': '#1f5eff', 'fill-opacity': dark ? 0.16 : 0.12 } })
      map.addLayer({ id: 'incident-region-boundary', type: 'line', source: regionSourceId, paint: { 'line-color': '#1f5eff', 'line-opacity': 0.85, 'line-width': 1.5, 'line-dasharray': [3, 2] } })
      map.addSource(sourceId, { type: 'geojson', data: dataRef.current, cluster: true, clusterMaxZoom: SPREAD_ZOOM - 1, clusterRadius: 38, clusterProperties: { killed_sum: ['+', ['to-number', ['get', 'killed_n'], 0]] } })
      map.addLayer({ id: 'clusters', type: 'circle', source: sourceId, filter: ['has', 'point_count'], paint: {
        'circle-color': ['step', ['get', 'killed_sum'], '#fbbf24', 10, '#f97316', 30, '#ef4444', 100, '#b91c1c', 300, '#7f1d1d'],
        'circle-radius': ['step', ['get', 'point_count'], 15, 5, 19, 15, 24, 40, 30], 'circle-opacity': 0.88,
        'circle-stroke-color': dark ? '#0f172a' : '#ffffff', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'cluster-count', type: 'symbol', source: sourceId, filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12 }, paint: { 'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,0.45)', 'text-halo-width': 1 } })
      const circle = {
        'circle-color': pointColor(colorRef.current, selectedIdRef.current || ''),
        'circle-radius': ['case', ['==', ['get', 'is_incident_location'], false], 7, ['interpolate', ['linear'], killed, 0, 6, 5, 9, 20, 15, 60, 24]],
        'circle-opacity': 0.92, 'circle-stroke-color': dark ? '#0f172a' : '#ffffff', 'circle-stroke-width': 1.5 } as never
      map.addLayer({ id: 'unclustered', type: 'circle', source: sourceId, filter: ['!', ['has', 'point_count']], maxzoom: SPREAD_ZOOM, paint: circle })
      map.addSource(leadersId, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({ id: 'incident-leaders', type: 'line', source: leadersId, minzoom: SPREAD_ZOOM, paint: { 'line-color': dark ? '#94a3b8' : '#475569', 'line-width': 1, 'line-opacity': 0.7 } })
      map.addSource(pointsId, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({ id: 'points', type: 'circle', source: pointsId, minzoom: SPREAD_ZOOM, paint: circle })
      spread()
    })
    map.on('load', () => {
      map.on('click', 'clusters', async (event) => {
        const feature = map.queryRenderedFeatures(event.point, { layers: ['clusters'] })[0]
        const clusterId = Number(feature?.properties?.cluster_id)
        const source = map.getSource(sourceId) as GeoJSONSource
        const zoom = await source.getClusterExpansionZoom(clusterId)
        map.easeTo({ center: (feature.geometry as unknown as GeoJSON.Point).coordinates as [number, number], zoom })
      })
      for (const layer of ['unclustered', 'points']) {
        map.on('click', layer, (event) => {
          const id = String(event.features?.[0]?.properties?.incident_id || '')
          if (id) onSelectRef.current(id)
        })
      }
      // Hover card: stays open while the pointer is on the point or on the card itself.
      let popup: maplibregl.Popup | undefined
      let closeTimer: number | undefined
      const hold = () => window.clearTimeout(closeTimer)
      const release = () => { closeTimer = window.setTimeout(() => { popup?.remove(); popup = undefined }, 350) }
      const showCard = (event: maplibregl.MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        if (!feature) return
        hold()
        popup?.remove()
        const content = buildPopup(feature.properties as never, (id) => { popup?.remove(); onOpenRef.current?.(id) })
        content.addEventListener('mouseenter', hold)
        content.addEventListener('mouseleave', release)
        popup = new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: '360px', className: 'mg-popup-box' })
          .setLngLat((feature.geometry as GeoJSON.Point).coordinates as [number, number]).setDOMContent(content).addTo(map)
      }
      for (const layer of ['unclustered', 'points']) {
        map.on('mouseenter', layer, showCard)
        map.on('mouseleave', layer, release)
      }
      for (const layer of ['clusters', 'unclustered', 'points']) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      const bounds = map.getBounds()
      onBoundsRef.current([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map((v) => v.toFixed(4)).join(','))
    })
    map.on('zoomend', spread)
    map.on('moveend', () => {
      const bounds = map.getBounds()
      onBoundsRef.current([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map((v) => v.toFixed(4)).join(','))
    })
    mapRef.current = map
    return () => { map.remove(); mapRef.current = undefined }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    ;(map?.getSource(sourceId) as GeoJSONSource | undefined)?.setData(data as never)
    ;(map?.getSource(regionSourceId) as GeoJSONSource | undefined)?.setData(selectedRegion(data, selectedId) as never)
    spreadRef.current?.()
  }, [data, selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getLayer('unclustered')) return
    for (const layer of ['unclustered', 'points']) map.setPaintProperty(layer, 'circle-color', pointColor(colorBy, selectedId || ''))
    if (selectedId) {
      const feature = data.features.find((item) => item.properties?.incident_id === selectedId)
      if (feature) map.easeTo({ center: feature.geometry.coordinates as [number, number], zoom: Math.max(map.getZoom(), SPREAD_ZOOM), duration: 500 })
    }
  }, [selectedId, colorBy, data])

  useEffect(() => {
    themeRef.current = theme
    const map = mapRef.current
    if (map && appliedThemeRef.current !== theme) {
      appliedThemeRef.current = theme
      map.setStyle(theme === 'dark' ? darkStyle : lightStyle)
    }
  }, [theme])

  return <div ref={container} className={`h-full min-h-[320px] w-full ${className}`} aria-label="World map of road accidents" />
}
