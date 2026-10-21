import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AspectStat } from "../types";
import { SENTIMENT_COLOR } from "../lib/format";

export default function AspectChart({ aspects, minMentions }: { aspects: AspectStat[]; minMentions: number }) {
  const shown = aspects.filter((a) => a.sufficient_evidence);
  const hidden = aspects.filter((a) => !a.sufficient_evidence);
  const data = shown.map((a) => ({ name: a.label, Positive: a.positive, Neutral: a.neutral, Negative: a.negative, mentions: a.mentions }));
  return (
    <div>
      {shown.length > 0 ? (
        <div role="img" aria-label={`Aspect sentiment: ${shown.map((a) => `${a.label} ${a.positive} positive, ${a.neutral} neutral, ${a.negative} negative`).join("; ")}`}>
          <ResponsiveContainer width="100%" height={Math.max(160, shown.length * 46 + 50)}>
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid horizontal={false} stroke="#E6DAC4" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="name" width={104} tick={{ fontSize: 13 }} />
              <Tooltip cursor={{ fill: "rgba(0,0,0,.04)" }} />
              <Legend />
              <Bar dataKey="Positive" stackId="a" fill={SENTIMENT_COLOR.positive} />
              <Bar dataKey="Neutral" stackId="a" fill={SENTIMENT_COLOR.neutral} />
              <Bar dataKey="Negative" stackId="a" fill={SENTIMENT_COLOR.negative} />
            </BarChart>
          </ResponsiveContainer>
          <p className="sr-only">Bars show how many reviews mention each aspect, split by sentiment.</p>
        </div>
      ) : (
        <p className="rounded-lg bg-paper px-3 py-4 text-sm text-muted">No aspect has at least {minMentions} mentions yet, so none are scored. Scores appear once there is enough review evidence.</p>
      )}
      {hidden.length > 0 && shown.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Not shown (fewer than {minMentions} mentions): {hidden.map((a) => `${a.label} (${a.mentions})`).join(", ")}.
        </p>
      )}
    </div>
  );
}
