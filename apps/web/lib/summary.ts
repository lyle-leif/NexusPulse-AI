/** The text that gets copied: title, dates, summary, evidence and next steps. */
export function summaryText(o: { title: string; dates: string; summary: string[]; evidence: string; nextSteps: string[]; link?: string }) {
  return [
    `${o.title} (${o.dates})`,
    "",
    ...o.summary.map((s) => `- ${s}`),
    "",
    `How well we can explain it: ${o.evidence}`,
    ...(o.nextSteps.length ? ["", "Next steps to check:", ...o.nextSteps.map((s) => `- ${s}`)] : []),
    ...(o.link ? ["", o.link] : []),
  ].join("\n");
}
