import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../lib/api'
import { SubmissionPage } from './SubmissionPage'

vi.mock('../lib/api', () => ({ api: { submit: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test('submits an HTML scrap ZIP to the moderation queue', async () => {
  vi.mocked(api.submit).mockResolvedValue({ submission_id: 'sub_test123', status: 'pending', submitted_at: '2026-08-11T00:00:00Z' })
  const bundle = new File(['zip-content'], 'incident.zip', { type: 'application/zip' })
  render(<SubmissionPage />)
  fireEvent.change(screen.getByLabelText('HTML scrap ZIP'), { target: { files: [bundle] } })
  fireEvent.change(screen.getByLabelText('Your name (optional)'), { target: { value: 'Contributor' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Submit for review' }).closest('form')!)
  expect(await screen.findByText('Submission received for review')).toBeInTheDocument()
  await waitFor(() => expect(api.submit).toHaveBeenCalledWith({ submission_type: 'html_bundle', package: bundle, submitter_name: 'Contributor' }))
})

test('switches to standalone video JSON input', () => {
  render(<SubmissionPage />)
  fireEvent.click(screen.getByText('Video analysis JSON'))
  expect(screen.getByLabelText('Video analysis JSON')).toHaveAttribute('accept', '.json,application/json')
  expect(screen.getByText('Upload the analysis JSON, not a raw video file.')).toBeInTheDocument()
})
