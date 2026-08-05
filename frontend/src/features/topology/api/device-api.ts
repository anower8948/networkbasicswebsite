/** Device configuration and CLI endpoints. */

import { apiClient } from '@/lib/api-client';
import type {
  CliResponse,
  CliSession,
  DeviceConfig,
  DeviceConfigResponse,
  DeviceViewResponse,
} from '@/types/device-config';
import type { TopologyDocument } from '@/types/topology';

export const deviceApi = {
  /** Validate a configuration and get its running-config plus warnings. */
  saveConfig: (document: TopologyDocument, deviceId: string, config: DeviceConfig) =>
    apiClient.post<DeviceConfigResponse>('/devices/config', { document, deviceId, config }),

  /** Rendered `show` output for the read-only tabs. */
  views: (document: TopologyDocument, deviceId: string, config: DeviceConfig) =>
    apiClient.post<DeviceViewResponse>('/devices/views', { document, deviceId, config }),

  /**
   * Run one command.
   *
   * The session travels with each line, so there is no server-side connection
   * state to expire.
   */
  runCommand: (
    document: TopologyDocument,
    deviceId: string,
    command: string,
    session: CliSession,
    config: DeviceConfig,
  ) =>
    apiClient.post<CliResponse>('/devices/cli', {
      document,
      deviceId,
      command,
      session,
      config,
    }),
};
