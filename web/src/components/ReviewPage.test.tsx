import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../lib/api'
import type { Submission } from '../types'
import { ReviewPage } from './ReviewPage'

vi.mock('../lib/api', () => ({ api: { reviewerMe: vi.fn(), reviewerLogin: vi.fn(), reviewerLogout: vi.fn(), reviewerSubmissions: vi.fn(), reviewerFileText: vi.fn(), reviewerDownloadUrl: vi.fn((id: string) => `/download/${id}`), reviewSubmission: vi.fn(), submissionStatus: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

const submission: Submission = {
  submission_id: 'sub_test123', status: 'pending', submission_type: 'html_bundle', title: 'incident.zip', original_filename: 'incident.zip', size_bytes: 2048, sha256: 'abc123', submitter_name: 'Contributor', submitted_at: '2026-08-11T00:00:00Z', loaded_source_ids: [], loaded_incident_ids: [], files: [{ file_id: 'upload_html', path: 'content.html', kind: 'html', size_bytes: 100, sha256: 'def456', preview_kind: 'text' }], audit: [{ action: 'submitted', actor: 'Contributor', at: '2026-08-11T00:00:00Z' }],
}

test('authenticated reviewer can preview and approve a queued package', async () => {
  vi.mocked(api.reviewerMe).mockResolvedValue({ username: 'alice', csrf_token: 'csrf-test' })
  vi.mocked(api.reviewerSubmissions).mockResolvedValue({ items: [submission], total: 1 })
  vi.mocked(api.reviewerFileText).mockResolvedValue('<html>Exact source</html>')
  vi.mocked(api.reviewSubmission).mockResolvedValue({ ...submission, status: 'approved', reviewed_by: 'alice' })
  const changed = vi.fn()
  render(<ReviewPage onDataChanged={changed} />)
  expect(await screen.findByText('incident.zip')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Download original ZIP' })).toHaveAttribute('href', '/download/sub_test123')
  fireEvent.click(screen.getByRole('button', { name: 'Preview text' }))
  expect(await screen.findByText('<html>Exact source</html>')).toBeInTheDocument()
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

test('background approval is polled without keeping the review request open', async () => {
  vi.mocked(api.reviewerMe).mockResolvedValue({ username: 'alice', csrf_token: 'csrf-test' })
  vi.mocked(api.reviewerSubmissions).mockResolvedValue({ items: [submission], total: 1 })
  vi.mocked(api.reviewSubmission).mockResolvedValue({ ...submission, status: 'processing', reviewed_by: 'alice' })
  vi.mocked(api.submissionStatus).mockResolvedValue({ submission_id: submission.submission_id, status: 'approved', submitted_at: submission.submitted_at })
  const changed = vi.fn()
  render(<ReviewPage onDataChanged={changed} />)
  expect(await screen.findByText('incident.zip')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Approve and load' }))
  expect(await screen.findByText('Approval completed and the refreshed pipeline data is available.')).toBeInTheDocument()
  expect(api.submissionStatus).toHaveBeenCalledWith('sub_test123')
  expect(changed).toHaveBeenCalled()
})
