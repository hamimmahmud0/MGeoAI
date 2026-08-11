import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../lib/api'
import { SubmissionPage } from './SubmissionPage'

vi.mock('../lib/api', () => ({ api: { submit: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test('submits pasted incident text to the moderation queue', async () => {
  vi.mocked(api.submit).mockResolvedValue({ submission_id: 'sub_test123', status: 'pending', submitted_at: '2026-08-11T00:00:00Z' })
  render(<SubmissionPage />)
  fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Runtime road collision' } })
  fireEvent.change(screen.getByLabelText('Publisher (optional)'), { target: { value: 'Test News' } })
  fireEvent.change(screen.getByLabelText('Scrap content as text'), { target: { value: 'A bus collision was reported on Test Road with traffic disruption.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))
  expect(await screen.findByText('Submission received for review')).toBeInTheDocument()
  await waitFor(() => expect(api.submit).toHaveBeenCalledWith(expect.objectContaining({ title: 'Runtime road collision', publisher: 'Test News' })))
})
