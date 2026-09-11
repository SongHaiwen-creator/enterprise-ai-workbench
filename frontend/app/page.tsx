"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type HealthState = "checking" | "healthy" | "unavailable";

export default function Home() {
  const [healthState, setHealthState] = useState<HealthState>("checking");

  useEffect(() => {
    const abortController = new AbortController();

    async function checkBackendHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, {
          signal: abortController.signal,
        });
        const data: unknown = await response.json();

        const isHealthy =
          response.ok &&
          typeof data === "object" &&
          data !== null &&
          "status" in data &&
          data.status === "ok";

        setHealthState(isHealthy ? "healthy" : "unavailable");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setHealthState("unavailable");
      }
    }

    void checkBackendHealth();

    return () => abortController.abort();
  }, []);

  const statusLabel = {
    checking: "Checking backend…",
    healthy: "Backend connected",
    unavailable: "Backend unavailable",
  }[healthState];

  return (
    <main>
      <section className="card">
        <p className="eyebrow">Application foundation</p>
        <h1>Enterprise AI Workbench</h1>
        <p className="summary">The frontend and backend are ready for incremental development.</p>
        <p className={`status status-${healthState}`} role="status">
          <span aria-hidden="true" />
          {statusLabel}
        </p>
      </section>
    </main>
  );
}
