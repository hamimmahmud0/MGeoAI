export type ColorBy = 'severity' | 'vehicle' | 'year'

export const SEVERITY_STEPS: [number, string, string][] = [[0, '#fbbf24', '0-1'], [2, '#f97316', '2-4'], [5, '#ef4444', '5-9'], [10, '#b91c1c', '10-19'], [20, '#7f1d1d', '20+']]
export const VEHICLE_COLORS: [string, string, string][] = [['bus', '#2563eb', 'bus'], ['truck', '#d97706', 'truck / pickup'], ['car', '#059669', 'car / microbus'], ['two_wheeler', '#7c3aed', 'motorcycle / rickshaw'], ['train', '#0891b2', 'train'], ['other', '#6b7280', 'other / unknown']]
export const YEAR_COLORS: [number, string][] = [[2025, '#0ea5e9'], [2026, '#f43f5e']]

