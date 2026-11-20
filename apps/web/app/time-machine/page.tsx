import Nav from "../components/Nav";
import TimeMachine from "./TimeMachine";

export const metadata = { title: "Time Machine | NexusPulse AI" };

export default function TimeMachinePage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-5 sm:px-6">
      <Nav active="time-machine" />
      <header>
        <p className="eyebrow">Replay</p>
        <h1 className="page-title mt-2">Time Machine</h1>
        <p className="muted mt-1">Replay the store one day at a time and see what the system knew on each day: what it expected, what it flagged, and how it explained it.</p>
      </header>
      <TimeMachine />
    </main>
  );
}
