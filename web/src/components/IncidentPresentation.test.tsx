import { describe, expect, it } from 'vitest'
import { formatCasualtyFact, formatValue } from '../lib/incidentPresentation'
import { regionData } from '../lib/mapRegions'

describe('incident presentation contracts', () => {
  it('shows conflicting casualty counts instead of object strings', () => {
    const fact = {
      field: 'fatalities', value: null, state: 'known', confidence: 0.8,
      conflicting_values: [{ count: 8 }, { count: 9 }], support_evidence_ids: [],
      contradiction: true, selection_rationale: 'sources conflict',
    }
    expect(formatCasualtyFact(fact)).toBe('8 vs 9 reported')
    expect(formatValue({ count: 8, source: 'a' })).toBe('8')
  })

  it('draws an uncertainty polygon for road segments', () => {
    const data: GeoJSON.FeatureCollection<GeoJSON.Point> = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature', id: 'inc',
        properties: { uncertainty_radius_km: 1, granularity: 'road_segment' },
        geometry: { type: 'Point', coordinates: [90.4, 23.8] },
      }],
    }
    const regions = regionData(data)
    expect(regions.features).toHaveLength(1)
    expect(regions.features[0].geometry.coordinates[0]).toHaveLength(65)
  })
})
