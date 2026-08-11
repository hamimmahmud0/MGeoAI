import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { App } from './App'

vi.mock('./components/MapView', () => ({ MapView: () => <div aria-label="Road and region map of traffic incidents" /> }))
vi.mock('./components/CoverageMap', () => ({ CoverageMap: () => <div aria-label="Collection-country source coverage map" /> }))
vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 50, type: 'FeatureCollection', features: [] }) })) as unknown as typeof fetch)

afterEach(cleanup)

test('renders operational map and accessible filters', () => {
  render(<App />)
  expect(screen.getByText('MGeoAI')).toBeInTheDocument()
  expect(screen.getByLabelText('Road and region map of traffic incidents')).toBeInTheDocument()
  expect(screen.getByLabelText('Severity')).toBeInTheDocument()
  expect(screen.getByText('Unmapped')).toBeInTheDocument()
})

test('defaults to system theme and allows an explicit override', () => {
  window.localStorage.removeItem('mgeoai-theme')
  window.localStorage.removeItem('traffic-fusion-theme')
  render(<App />)
  const theme = screen.getByLabelText('Theme')
  expect(theme).toHaveValue('system')
  fireEvent.change(theme, { target: { value: 'dark' } })
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem('mgeoai-theme')).toBe('dark')
})

test('labels global coverage centroids as non-incident locations', () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Global coverage' }))
  expect(screen.getByLabelText('Collection-country source coverage map')).toBeInTheDocument()
  expect(screen.getByText(/not reported crash locations/i)).toBeInTheDocument()
})
