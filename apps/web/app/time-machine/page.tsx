import Nav from "../components/Nav";
import TimeMachine from "./TimeMachine";

export const metadata = { title: "Time Machine | NexusPulse AI" };

export default function TimeMachinePage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <Nav active="time-machine" />
      <header>
        <p className="eyebrow">NexusPulse AI</p>
        <h1 className="text-2xl font-semibold tracking-tight">Time Machine</h1>
        <p className="muted">Step through the store day by day and see what the monitor knew on each day: forecast, detection and investigation.</p>
      </header>
      <TimeMachine />
    </main>
  );
}
