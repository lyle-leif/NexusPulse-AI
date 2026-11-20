"use client";

import { useCallback, useEffect, useState } from "react";
import { STATIC_DEMO, getTimeMachineDay, getTimeMachineReport, type TimeMachineDay, type TmReport } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import ForecastChart from "../components/ForecastChart";
import IssueCard, { issueTitle } from "../components/IssueCard";
import CopySummary from "../components/CopySummary";
import { summaryText } from "@/lib/summary";
import Icon from "../components/Icons";
import { EvidenceMeter } from "../components/Mini";
import { SkeletonBlock, SkeletonCard } from "../components/Skeleton";

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** What the monitor knew at the end of the selected day, in one sentence. */
function knewSentence(tm: TimeMachineDay) {
  const last = tm.series.at(-1);
  const today = last
    ? last.state === "out_of_range"
      ? `Revenue today (${money(last.actual, tm.workspace.currency)}) was outside the expected range.`
      : `Revenue today (${money(last.actual, tm.workspace.currency)}) was within the expected range.`
    : "";
  const open = tm.incidents.filter((i) => i.end === null && i.status !== "suppressed_data_quality");
  const newToday = tm.incidents.filter((i) => i.start === tm.day || i.members.some((m) => m.start === tm.day));
  return `${today} ${
    open.length ? `${open.length} open issue${open.length > 1 ? "s" : ""}: ${issueTitle(open[0]).toLowerCase()} since ${shortDate(open[0].start)}.` : "No open issues."
  }${newToday.length ? " A new signal appeared today." : ""}`;
}

export default function TimeMachine() {
  const [day, setDay] = useState<string | undefined>(undefined);
  const [tm, setTm] = useState<TimeMachineDay | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [rep, setRep] = useState<TmReport | null>(null);
  const [repErr, setRepErr] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let live = true;
    getTimeMachineDay(day)
      .then((d) => live && (setTm(d), setErr(null)))
      .catch((e) => live && setErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [day]);

  useEffect(() => {
    setRep(null);
    setRepErr(null);
    if (!sel || !tm) return;
    let live = true;
    // The static demo stores investigations for the day an issue is first detected and
    // the day it ends; it shows the latest of those up to the selected day.
    const inc = tm.incidents.find((i) => i.incident_id === sel);
    if (!inc) {
      setSel(null);
      return;
    }
    const repDay = STATIC_DEMO ? inc.static_report_day : tm.day;
    if (!repDay) {
      setRepErr(STATIC_DEMO ? "Not investigated in the static demo (tracking problem)." : "Unknown issue.");
      return;
    }
    getTimeMachineReport(repDay, sel)
      .then((r) => live && setRep(r))
      .catch((e) => live && setRepErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [sel, tm]);

  const go = useCallback(
    (d: string) => {
      if (!tm) return;
      setDay(d < tm.first_day ? tm.first_day : d > tm.last_day ? tm.last_day : d);
    },
    [tm],
  );

  useEffect(() => {
    if (!playing || !tm) return;
    if (tm.day >= tm.last_day) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => go(addDays(tm.day, 1)), 600);
    return () => clearTimeout(t);
  }, [playing, tm, go]);

  if (err) return <p role="alert">Could not load the Time Machine: {err}. Is the API running?</p>;
  if (!tm)
    return (
      <div className="space-y-5" aria-busy="true">
        <p className="sr-only" role="status">Loading the Time Machine</p>
        <SkeletonCard lines={2} />
        <SkeletonCard chart lines={0} />
      </div>
    );
  const cur = tm.workspace.currency;
  const dayIdx = Math.round((Date.parse(tm.day) - Date.parse(tm.first_day)) / 86400000);
  const total = Math.round((Date.parse(tm.last_day) - Date.parse(tm.first_day)) / 86400000);

  return (
    <div className="space-y-5">
      <section className="card bracket" aria-labelledby="ctl">
        <h2 id="ctl" className="sr-only">
          Controls
        </h2>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label">Viewing the store as of</p>
            <p className="hero-value" style={{ fontSize: "2.2rem" }}>
              {shortDate(tm.day)}
            </p>
            <p className="faint text-xs">
              Day {dayIdx + 1} of {total + 1}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="pill" onClick={() => go(addDays(tm.day, -1))} disabled={tm.day <= tm.first_day}>
              Back a day
            </button>
            <button className="pill" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
              {playing ? "Pause" : "Play"}
            </button>
            <button className="pill" onClick={() => go(addDays(tm.day, 1))} disabled={tm.day >= tm.last_day}>
              Next day
            </button>
            <button className="pill" onClick={() => go(addDays(tm.day, 7))} disabled={tm.day >= tm.last_day}>
              Next week
            </button>
            <button className="pill" onClick={() => tm.next_incident_day && go(tm.next_incident_day)} disabled={!tm.next_incident_day}>
              Jump to next new issue
            </button>
          </div>
        </div>
        <label className="mt-4 block">
          <span className="sr-only">Day</span>
          <input
            type="range"
            min={0}
            max={total}
            value={dayIdx}
            className="w-full"
            style={{ ["--fill" as string]: `${total ? (100 * dayIdx) / total : 0}%` }}
            onChange={(e) => go(addDays(tm.first_day, Number(e.target.value)))}
          />
        </label>
        <p className="status-sentence mt-3">{knewSentence(tm)}</p>
      </section>

      <section className="card" aria-labelledby="chart">
        <div className="card-head">
          <h2 id="chart" className="section-title"><Icon name="chart" /> Revenue vs expected, as of this day</h2>
          <span className="faint text-xs">Nothing after this day is used</span>
        </div>
        <ForecastChart
          past={tm.series}
          ahead={tm.forecast_ahead}
          currency={cur}
          spans={tm.incidents.filter((i) => i.status !== "suppressed_data_quality").map((i) => ({ id: i.incident_id, start: i.start, end: i.end, direction: i.direction }))}
          label={`Net revenue up to ${tm.day} with the range expected for each day, and the forecast for the coming days`}
        />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card" aria-labelledby="inc">
          <div className="card-head">
            <h2 id="inc" className="section-title"><Icon name="issue" /> Issues known on this day</h2>
            <span className="faint text-xs">{tm.incidents.length}</span>
          </div>
          {tm.incidents.length === 0 ? (
            <p className="muted text-sm">Nothing unusual detected yet.</p>
          ) : (
            <ul className="space-y-2">
              {tm.incidents.slice(0, 8).map((i) => (
                <IssueCard
                  key={i.incident_id}
                  i={i}
                  currency={cur}
                  action={
                    i.status === "suppressed_data_quality" ? undefined : (
                      <button className="link text-sm" onClick={() => setSel(i.incident_id)} aria-pressed={sel === i.incident_id}>
                        {sel === i.incident_id ? "Investigating" : "Investigate as of this day"}
                      </button>
                    )
                  }
                />
              ))}
            </ul>
          )}
        </section>

        <section className="card solid" aria-labelledby="rep" aria-live="polite">
          <div className="card-head">
            <h2 id="rep" className="section-title"><Icon name="search" /> Investigation as of {shortDate(rep?.day ?? tm.day)}</h2>
            {rep && sel ? (
              <CopySummary
                text={summaryText({
                  title: issueTitle(tm.incidents.find((i) => i.incident_id === sel) ?? tm.incidents[0]),
                  dates: `as of ${shortDate(rep.day)}`,
                  summary: rep.report.summary.map((x) => x.text),
                  evidence: rep.evidence.level,
                  nextSteps: rep.report.next_steps.map((x) => x.text),
                })}
              />
            ) : null}
          </div>
          {STATIC_DEMO && rep && rep.day !== tm.day ? (
            <p className="faint mb-2 text-xs">Static demo: investigations are stored for the detection day and the end day. The live app runs one for any day.</p>
          ) : null}
          {!sel ? (
            <p className="muted text-sm">Choose an issue. It is investigated with data up to the end of this day only.</p>
          ) : repErr ? (
            <p className="text-sm">{repErr}</p>
          ) : !rep ? (
            <div className="space-y-3" aria-busy="true">
              <p className="sr-only" role="status">Investigating</p>
              <SkeletonBlock h={10} w="40%" />
              <SkeletonBlock h={8} />
              <SkeletonBlock h={12} w="90%" />
              <SkeletonBlock h={12} w="75%" />
              <SkeletonBlock h={12} w="60%" />
            </div>
          ) : (
            <div className="space-y-4 text-sm">
              <div>
                <p className="label mb-2">How well we can explain it</p>
                <EvidenceMeter level={rep.evidence.level} />
              </div>
              <ul className="lead space-y-2" style={{ fontSize: "0.95rem" }}>
                {rep.report.summary.map((s, k) => (
                  <li key={k}>{s.text}</li>
                ))}
              </ul>
              {rep.report.next_steps.length ? (
                <div>
                  <p className="sub-title">Next steps to check</p>
                  <ul className="list-disc space-y-1 pl-5">
                    {rep.report.next_steps.map((s) => (
                      <li key={s.id}>{s.text}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </section>
      </div>

      <section className="card solid" aria-labelledby="ev">
        <h2 id="ev" className="section-title"><Icon name="clock" /> Recorded changes in the last 30 days</h2>
        {tm.events.length === 0 ? (
          <p className="muted text-sm">None.</p>
        ) : (
          <ol className="space-y-2 border-l pl-4 text-sm" style={{ borderColor: "var(--border)" }}>
            {tm.events.map((e) => (
              <li key={e.occurred_at + e.description}>
                <span className="faint num text-xs">{shortDate(e.occurred_at.slice(0, 10))}</span> {e.description}{" "}
                <span className="faint">({e.event_type.replaceAll("_", " ")})</span>
              </li>
            ))}
          </ol>
        )}
      </section>
      <p className="faint text-xs">
        {tm.data_label} data. Each day shows exactly what the monitor knew at the end of that day: forecasts are made before the days they cover, and
        investigations use no later data.
      </p>
    </div>
  );
}
