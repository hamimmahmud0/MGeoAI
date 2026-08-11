import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../lib/api'
import type { Submission } from '../types'
import { ReviewPage } from './ReviewPage'

vi.mock('../lib/api', () => ({ api: { reviewerMe: vi.fn(), reviewerLogin: vi.fn(), reviewerLogout: vi.fn(), reviewerSubmissions: vi.fn(), reviewSubmission: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

const submission: Submission = {
  submission_id: 'sub_test123', status: 'pending', source_kind: 'news', title: 'Runtime crash report', publisher: 'Test News', content: 'A bus collision was reported on Test Road.', submitter_name: 'Contributor', submitted_at: '2026-08-11T00:00:00Z', loaded_source_ids: [], loaded_incident_ids: [], audit: [{ action: 'submitted', actor: 'Contributor', at: '2026-08-11T00:00:00Z' }],
}

test('authenticated reviewer can approve a queued submission', async () => {
  vi.mocked(api.reviewerMe).mockResolvedValue({ username: 'alice', csrf_token: 'csrf-test' })
  vi.mocked(api.reviewerSubmissions).mockResolvedValue({ items: [submission], total: 1 })
  vi.mocked(api.reviewSubmission).mockResolvedValue({ ...submission, status: 'approved', reviewed_by: 'alice' })
  const changed = vi.fn()
  render(<ReviewPage onDataChanged={changed} />)
  expect(await screen.findByText('Runtime crash report')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Review note'), { target: { value: 'Reviewed source.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Approve and load' }))
  await waitFor(() => expect(api.reviewSubmission).toHaveBeenCalledWith('sub_test123', 'approve', 'Reviewed source.', 'csrf-test'))
  expect(changed).toHaveBeenCalled()
})

test('unauthenticated reviewer sees the login form', async () => {
  vi.mocked(api.reviewerMe).mockRejectedValue(new Error('Reviewer login required'))
  render(<ReviewPage onDataChanged={vi.fn()} />)
  expect(await screen.findByRole('heading', { name: 'Reviewer login' })).toBeInTheDocument()
  expect(screen.getByLabelText('Username')).toBeInTheDocument()
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
})
