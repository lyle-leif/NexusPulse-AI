import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CopySummary from "@/app/components/CopySummary";
import IntroBanner from "@/app/components/IntroBanner";
import ThemeToggle from "@/app/components/ThemeToggle";
import { summaryText } from "@/lib/summary";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("ThemeToggle", () => {
  it("switches to light and back, and remembers the choice", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("np-theme")).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("np-theme")).toBe("dark");
  });

  it("starts in light mode when the page already is", () => {
    document.documentElement.dataset.theme = "light";
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeTruthy();
  });
});

describe("CopySummary", () => {
  it("copies the text and announces it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CopySummary text="Visits fell" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /copy summary/i })));
    expect(writeText).toHaveBeenCalledWith("Visits fell");
    expect(screen.getByRole("status").textContent).toBe("Copied");
  });

  it("falls back to a hidden text area when the clipboard is blocked", async () => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) }, configurable: true });
    const exec = vi.fn().mockReturnValue(false);
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    render(<CopySummary text="Visits fell" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /copy summary/i })));
    expect(exec).toHaveBeenCalledWith("copy");
    expect(screen.getByRole("status").textContent).toBe("Could not copy");
    expect(document.querySelector("textarea")).toBeNull(); // the helper is removed again
  });
});

describe("IntroBanner", () => {
  it("shows on the first visit and stays hidden after Dismiss", () => {
    const first = render(<IntroBanner />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("complementary", { name: "About this demo" })).toBeNull();
    expect(localStorage.getItem("np-intro-seen")).toBe("1");
    first.unmount();

    render(<IntroBanner />);
    expect(screen.queryByRole("complementary", { name: "About this demo" })).toBeNull();
  });

  it("shows for a new visitor", () => {
    render(<IntroBanner />);
    expect(screen.getByRole("complementary", { name: "About this demo" })).toBeTruthy();
  });
});

describe("summaryText", () => {
  it("lists the summary, evidence and next steps as plain text", () => {
    const text = summaryText({
      title: "Visits lower than expected",
      dates: "May 14 to May 17, 2026",
      summary: ["Net revenue fell.", "Paid search moved most."],
      evidence: "Moderate",
      nextSteps: ["Check the campaign budget."],
      link: "https://example.test/i/1",
    });
    expect(text).toBe(
      [
        "Visits lower than expected (May 14 to May 17, 2026)",
        "",
        "- Net revenue fell.",
        "- Paid search moved most.",
        "",
        "How well we can explain it: Moderate",
        "",
        "Next steps to check:",
        "- Check the campaign budget.",
        "",
        "https://example.test/i/1",
      ].join("\n"),
    );
  });

  it("leaves out the next-steps block when there are none", () => {
    const text = summaryText({ title: "T", dates: "D", summary: ["S"], evidence: "Weak", nextSteps: [] });
    expect(text).not.toContain("Next steps");
  });
});
