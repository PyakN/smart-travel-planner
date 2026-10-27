import { formatDate, formatTemp, weatherIcon } from "@/lib/format";
import type { DayForecast } from "@/lib/types";

export interface DayWeatherProps {
  date: string | null;
  forecast: DayForecast | null;
}

function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The day's date and the forecast for its sightseeing hours, in 3-hour slots. */
export default function DayWeather({ date, forecast }: DayWeatherProps) {
  if (!date) return null;
  if (!forecast) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 bg-white px-3 py-2 text-xs text-zinc-500">
        <span className="font-medium text-zinc-700">{formatDate(date)}</span> · No forecast yet:
        forecasts reach 5 days ahead.
      </div>
    );
  }
  return (
    <section
      aria-label={`Weather on ${formatDate(date)}`}
      className="rounded-lg border border-zinc-200 bg-white p-3 shadow-sm"
    >
      <div className="flex items-center gap-3">
        <span className="text-3xl leading-none" aria-hidden>
          {weatherIcon(forecast)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-zinc-900">
            {formatDate(date)} · {sentenceCase(forecast.description)}
          </p>
          <p className="text-xs text-zinc-500">
            {forecast.temp_min_c}–{formatTemp(forecast.temp_max_c)}
            {forecast.pop > 0 && ` · ${forecast.pop}% chance of rain`} · daylight {forecast.sunrise}
            –{forecast.sunset}
          </p>
        </div>
      </div>
      <ol className="mt-2 flex gap-1 overflow-x-auto" aria-label="Forecast by time">
        {forecast.slots.map((slot) => (
          <li
            key={slot.time}
            title={slot.description}
            className="flex min-w-14 flex-1 flex-col items-center rounded-md bg-zinc-50 px-1.5 py-1 text-[11px] text-zinc-600"
          >
            <span className="tabular-nums">{slot.time}</span>
            <span className="text-base leading-tight" aria-label={slot.description}>
              {weatherIcon(slot)}
            </span>
            <span className="font-medium text-zinc-800">{formatTemp(slot.temp_c)}</span>
            <span className={slot.pop >= 50 ? "font-medium text-sky-700" : "text-zinc-400"}>
              {slot.pop}%
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
