/** Glass placeholder blocks shaped like the real cards, so the layout doesn't jump while data loads. */
export function SkeletonBlock({ h = 16, w = "100%", className = "" }: { h?: number; w?: number | string; className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} style={{ height: h, width: w }} />;
}

export function SkeletonCard({ lines = 3, chart = false }: { lines?: number; chart?: boolean }) {
  return (
    <div className="card space-y-3" aria-hidden>
      <SkeletonBlock h={12} w="35%" />
      {chart ? <SkeletonBlock h={200} /> : null}
      {Array.from({ length: lines }, (_, i) => (
        <SkeletonBlock key={i} h={12} w={`${90 - i * 12}%`} />
      ))}
    </div>
  );
}

/** Full-page placeholder: a header line, a row of tiles and two cards. */
export default function PageSkeleton({ label }: { label: string }) {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-5 sm:px-6" aria-busy="true">
      <p className="sr-only" role="status">
        {label}
      </p>
      <SkeletonBlock h={58} className="rounded-xl" />
      <SkeletonBlock h={42} w="45%" />
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <SkeletonCard key={i} lines={2} />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <SkeletonCard chart lines={1} />
        <SkeletonCard lines={5} />
      </div>
    </main>
  );
}
