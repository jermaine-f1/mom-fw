import { useEffect, useState } from "react";
import type { DataPayload } from "../types";

// Must match DATA_SCHEMA_VERSION in mom_gen.py. Bump both sides together.
const EXPECTED_SCHEMA_VERSION = 1;

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; payload: DataPayload };

function validate(raw: unknown): DataPayload {
  if (!raw || typeof raw !== "object") {
    throw new Error("data.json root is not an object");
  }
  const payload = raw as Partial<DataPayload>;

  if (typeof payload.schemaVersion !== "number") {
    throw new Error("data.json is missing a numeric schemaVersion field");
  }
  if (payload.schemaVersion !== EXPECTED_SCHEMA_VERSION) {
    throw new Error(
      `data.json schemaVersion=${payload.schemaVersion} but frontend expects ${EXPECTED_SCHEMA_VERSION}. ` +
        `Rebuild the frontend or regenerate data.json.`,
    );
  }
  if (typeof payload.generatedAt !== "string") {
    throw new Error("data.json is missing generatedAt (string)");
  }
  if (!Array.isArray(payload.etfUniverse)) {
    throw new Error("data.json is missing etfUniverse (array)");
  }
  if (
    !payload.correlations ||
    typeof payload.correlations !== "object" ||
    Array.isArray(payload.correlations)
  ) {
    throw new Error("data.json is missing correlations (object)");
  }
  return payload as DataPayload;
}

export function useData(): State {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch("/data.json", { cache: "no-cache" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching /data.json`);
        return res.json();
      })
      .then((raw) => validate(raw))
      .then((payload) => {
        if (!cancelled) setState({ status: "ready", payload });
      })
      .catch((err: Error) => {
        // Also log so silent failures show up in the browser console.
        console.error("Failed to load data.json", err);
        if (!cancelled)
          setState({ status: "error", message: err.message ?? String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
