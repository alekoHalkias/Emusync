interface EmusyncAPI {
  checkConfig(): Promise<{ configExists: boolean }>;
  getBackendPort(): Promise<number>;
  openFileDialog(options?: object): Promise<string | null>;
  openDirectoryDialog(): Promise<string | null>;
}

interface Window {
  emusync: EmusyncAPI;
}
