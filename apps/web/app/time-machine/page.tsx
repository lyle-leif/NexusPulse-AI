import Nav from "../components/Nav";
import TimeMachine from "./TimeMachine";

export const metadata = { title: "Time Machine | NexusPulse AI" };

export default function TimeMachinePage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <Nav active="time-machine" />
      <header>
        <p className="eyebrow">NexusPulse AI</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Time Machine</h1>
        <p className="muted">Replay the store one day at a time and see what the system knew on each day: what it expected, what it flagged, and how it explained it.</p>
      </header>
      <TimeMachine />
    </main>
  );
}
