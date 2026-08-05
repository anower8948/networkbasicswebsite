/** Topology editor endpoints. */

import { apiClient } from '@/lib/api-client';
import type { MessageResponse, Page } from '@/types/api';
import type {
  CableKind,
  DeviceSpec,
  LinkSuggestion,
  TopologyDocument,
  TopologyRead,
  TopologySummary,
} from '@/types/topology';

export interface TopologyExport {
  format: string;
  schemaVersion: number;
  name: string;
  description: string | null;
  document: TopologyDocument;
}

export const topologyApi = {
  /** Public and static — the palette needs it before anyone signs in. */
  deviceCatalog: () => apiClient.get<DeviceSpec[]>('/topologies/device-catalog'),

  list: (limit = 50, offset = 0) =>
    apiClient.get<Page<TopologySummary>>(`/topologies?limit=${limit}&offset=${offset}`),

  get: (id: string) => apiClient.get<TopologyRead>(`/topologies/${id}`),

  create: (name: string, document: TopologyDocument, description?: string) =>
    apiClient.post<TopologyRead>('/topologies', { name, description, document }),

  update: (id: string, changes: { name?: string; description?: string; document?: TopologyDocument }) =>
    apiClient.patch<TopologyRead>(`/topologies/${id}`, changes),

  remove: (id: string) => apiClient.delete<MessageResponse>(`/topologies/${id}`),

  duplicate: (id: string) => apiClient.post<TopologyRead>(`/topologies/${id}/duplicate`),

  exportOne: (id: string) => apiClient.get<TopologyExport>(`/topologies/${id}/export`),

  importOne: (name: string, document: TopologyDocument) =>
    apiClient.post<TopologyRead>('/topologies/import', { name, document }),

  /**
   * Ask the server which ports and cable a new link should use.
   *
   * Stateless — the editor posts its in-memory document, so this works before
   * a topology has ever been saved.
   */
  suggestLink: (
    document: TopologyDocument,
    source: string,
    target: string,
    cable?: CableKind,
  ) => {
    const params = new URLSearchParams({ source, target });
    if (cable) params.set('cable', cable);
    return apiClient.post<LinkSuggestion>(`/topologies/suggest-link?${params}`, document);
  },
};
