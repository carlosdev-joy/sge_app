import { apiFetch, apiFetchBruto } from './api'
import type { WorkspaceCapabilities, WorkspaceContext, WorkspaceDefinition, WorkspaceDraft, WorkspaceLayout, WorkspaceLease } from './workspace'
export const workspaceApi = {
 capabilities: (signal?: AbortSignal) => apiFetch<WorkspaceCapabilities>('/workspace/capabilities', { signal }),
 context: (name: string, signal?: AbortSignal) => apiFetch<WorkspaceContext>(`/workspace/pipeline-context?${new URLSearchParams({ name })}`, { signal }),
 draft: (id: string, signal?: AbortSignal) => apiFetch<WorkspaceDraft>(`/workspace/drafts/${encodeURIComponent(id)}`, { signal }),
 create: (definition: WorkspaceDefinition, layout: WorkspaceLayout) => apiFetch<WorkspaceDraft>('/workspace/pipelines', { method: 'POST', body: JSON.stringify({ definition, layout }) }),
 import: (name: string) => apiFetch<WorkspaceDraft>(`/workspace/pipeline-drafts?${new URLSearchParams({ name })}`, { method: 'POST' }),
 save: (draft: WorkspaceDraft, definition: WorkspaceDefinition, layout: WorkspaceLayout, fence: number) => apiFetch<WorkspaceDraft>(`/workspace/drafts/${draft.draftId}`, { method: 'PUT', body: JSON.stringify({ expectedRevision: draft.revision, fence, definition, layout }) }),
 lease: (id: string, fence?: number) => apiFetch<WorkspaceLease>(`/workspace/drafts/${id}/lease`, { method: 'POST', body: JSON.stringify(fence === undefined ? {} : { fence }) }),
 transfer: (draft: WorkspaceDraft, fence: number) => apiFetch<WorkspaceLease>(`/workspace/drafts/${draft.draftId}/transfer`, { method: 'POST', body: JSON.stringify({ expectedRevision: draft.revision, fence }) }),
 release: async (draft: WorkspaceDraft, fence: number) => { await apiFetchBruto(`/workspace/drafts/${draft.draftId}/lease`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expectedRevision: draft.revision, fence }) }) },
 discard: async (draft: WorkspaceDraft, fence: number) => { await apiFetchBruto(`/workspace/drafts/${draft.draftId}`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expectedRevision: draft.revision, fence }) }) },
}
