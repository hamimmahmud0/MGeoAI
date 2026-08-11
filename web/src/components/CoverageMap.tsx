import { useEffect, useRef } from 'react'
import maplibregl, { type GeoJSONSource, type Map } from 'maplibre-gl'
import type { CoverageCollection } from '../types'

type Props = { data: CoverageCollection; theme: 'light' | 'dark' }

const sourceId = 'country-coverage'
const lightStyle = import.meta.env.VITE_MAP_STYLE_LIGHT_URL || import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty'
const darkStyle = import.meta.env.VITE_MAP_STYLE_DARK_URL || 'https://tiles.openfreemap.org/styles/dark'

export function CoverageMap({ data, theme }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map>()
  const dataRef = useRef(data)
  const themeRef = useRef(theme)
  dataRef.current = data

  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: themeRef.current === 'dark' ? darkStyle : lightStyle,
      center: [12, 18],
      zoom: 1.1,
      attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.on('style.load', () => {
      if (map.getSource(sourceId)) return
      map.addSource(sourceId, { type: 'geojson', data: dataRef.current })
      map.addLayer({
        id: 'country-coverage-points',
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-color': '#1f5eff',
          'circle-opacity': 0.82,
          'circle-radius': ['interpolate', ['linear'], ['get', 'accepted_sources'], 0, 6, 10, 10, 20, 14],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
        },
      })
      map.addLayer({
        id: 'country-coverage-labels',
        type: 'symbol',
        source: sourceId,
        layout: {
          'text-field': ['get', 'iso3'],
          'text-size': 10,
          'text-offset': [0, 1.5],
          'text-anchor': 'top',
          'text-allow-overlap': false,
        },
        paint: {
          'text-color': themeRef.current === 'dark' ? '#dbe7ff' : '#173b85',
          'text-halo-color': themeRef.current === 'dark' ? '#101828' : '#ffffff',
          'text-halo-width': 1.5,
        },
      })
    })
    map.on('load', () => {
      map.on('click', 'country-coverage-points', (event) => {
        const feature = event.features?.[0]
        if (!feature || feature.geometry.type !== 'Point') return
        const properties = feature.properties || {}
        const content = document.createElement('div')
        content.className = 'text-sm'
        const title = document.createElement('strong')
        title.textContent = String(properties.country_name || properties.iso3 || 'Country')
        const detail = document.createElement('p')
        detail.textContent = `${properties.accepted_sources || 0} accepted sources · ${properties.reviewed_multi_source_incidents || 0} multi-source incident(s)`
        content.append(title, detail)
        new maplibregl.Popup()
          .setLngLat((feature.geometry as GeoJSON.Point).coordinates as [number, number])
          .setDOMContent(content)
          .addTo(map)
      })
      map.on('mouseenter', 'country-coverage-points', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'country-coverage-points', () => { map.getCanvas().style.cursor = '' })
    })
    mapRef.current = map
    return () => { map.remove(); mapRef.current = undefined }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource(sourceId) as GeoJSONSource | undefined
    source?.setData(data as never)
  }, [data])

  useEffect(() => {
    themeRef.current = theme
    mapRef.current?.setStyle(theme === 'dark' ? darkStyle : lightStyle)
  }, [theme])

  return <div ref={container} className="h-full min-h-[460px] w-full" aria-label="Collection-country source coverage map" />
}
