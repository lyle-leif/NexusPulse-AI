"use client";

export default function Error({ error }: { error: Error }) {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-2 px-4 py-8 sm:px-6">
      <h1 className="text-xl font-semibold">Could not load the overview</h1>
      <p className="muted">{error.message}</p>
      <p className="muted text-sm">
        Check that Postgres is running (docker compose up -d) and the API is running (uv run uvicorn main:app --app-dir services/api --port 8000).
      </p>
    </main>
  );
}
