import { useEffect, useState } from "react";
import type { DataPayload } from "../types";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; payload: DataPayload };

export function useData(): State {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch("/data.json", { cache: "no-cache" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as DataPayload;
      })
      .then((payload) => {
        if (!cancelled) setState({ status: "ready", payload });
      })
      .catch((err: Error) => {
        if (!cancelled)
          setState({ status: "error", message: err.message ?? String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
