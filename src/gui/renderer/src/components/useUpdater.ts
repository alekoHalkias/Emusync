import { useCallback, useEffect, useState } from "react";

export type UpdateStatus = "idle" | "update-available" | "update-downloaded" | "error";

interface UpdateEvent {
  type: string;
  releaseNotes?: string;
  releaseVersion?: string;
  message?: string;
}

export function useUpdater(): {
  status: UpdateStatus;
  releaseNotes: string;
  releaseVersion: string;
  errorMessage: string;
  checkForUpdate: () => void;
  downloadUpdate: () => void;
  installUpdate: () => void;
} {
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [releaseVersion, setReleaseVersion] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const checkForUpdate = useCallback(() => {
    window.emusync.updater.check().then((res) => {
      if (res.available) {
        // Event will fire, just ensure we're clean
      }
    });
  }, []);

  const downloadUpdate = useCallback(() => {
    window.emusync.updater.download();
  }, []);

  const installUpdate = useCallback(() => {
    window.emusync.updater.install();
  }, []);

  useEffect(() => {
    const unsubscribe = window.emusync.updater.onChange((evt: UpdateEvent) => {
      switch (evt.type) {
        case "update-available":
          setStatus("update-available");
          setReleaseNotes(evt.releaseNotes ?? "");
          setReleaseVersion(evt.releaseVersion ?? "");
          break;
        case "update-downloaded":
          setStatus("update-downloaded");
          setReleaseNotes(evt.releaseNotes ?? "");
          setReleaseVersion(evt.releaseVersion ?? "");
          break;
        case "update-not-available":
          setStatus("idle");
          break;
        case "error":
          setStatus("error");
          setErrorMessage(evt.message ?? "An unknown error occurred.");
          break;
      }
    });
    return unsubscribe;
  }, []);

  return { status, releaseNotes, releaseVersion, errorMessage, checkForUpdate, downloadUpdate, installUpdate };
}
