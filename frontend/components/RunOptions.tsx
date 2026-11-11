"use client";

import { Select } from "./Select";
import { Switch } from "./ui";
import { useSettings } from "@/lib/settings";

export const EFFORTS = [
  { value: "low" as const, label: "Low", hint: "Fastest, for small edits" },
  { value: "medium" as const, label: "Medium" },
  { value: "high" as const, label: "High", hint: "Recommended" },
  { value: "xhigh" as const, label: "Extra high" },
  { value: "max" as const, label: "Max", hint: "Slowest, most thorough" },
];

/** Per-message AI options; they persist as the user's defaults. */
export function RunOptions() {
  const [s, set] = useSettings();
  return (
    <>
      <div className="label">For this and next messages</div>
      <Switch small label="Apply automatically" hint="Skip the review step when Claude has no questions" checked={s.autoApply} onChange={(v) => set({ autoApply: v })} />
      <Switch small label="Review pass" hint="Claude re-reads the result and fixes anything missed" checked={s.review} onChange={(v) => set({ review: v })} />
      <Switch small label="Visual check" hint="Claude inspects the changed pages" checked={s.visual} onChange={(v) => set({ visual: v })} />
      <div className="row"><span className="grow">Effort</span>
        <Select small align="right" label="Effort" value={s.effort} onChange={(v) => set({ effort: v })} width={220} options={EFFORTS} /></div>
    </>
  );
}
