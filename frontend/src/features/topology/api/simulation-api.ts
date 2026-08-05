/** Packet simulation endpoint. */

import { apiClient } from '@/lib/api-client';
import type { SimulationRequest, SimulationResult } from '@/types/simulation';

export const simulationApi = {
  /**
   * Run one protocol exchange and get the full trace.
   *
   * Stateless — the editor posts the topology it currently has, so a learner
   * can experiment without saving.
   */
  run: (request: SimulationRequest) =>
    apiClient.post<SimulationResult>('/simulation/run', request),
};
