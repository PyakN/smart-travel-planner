import { Icon } from "@/components/ui/Icon";
import { dayHours, formatDate, formatTemp, weatherIcon } from "@/lib/format";
import type { PlannedDay } from "@/lib/types";

export interface DayWeatherProps {
  day: Pick<PlannedDay, "date" | "weather" | "start" | "end" | "sunset">;
  /** Weather-aware plans have the forecast of the day's hours; others never ask for one. */
  weatherAware: boolean;
}

function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The day's date and hours, and for weather-aware plans the forecast of those hours in
 * 3-hour slots. */
export default function DayWeather({ day, weatherAware }: DayWeatherProps) {
  const { date, weather: forecast } = day;
  if (!date) return null;
  const hours = dayHours(day);
  if (!weatherAware || !forecast) {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-panel bg-canvas px-3.5 py-2.5 text-small text-ink-2">
        <span className="flex items-center gap-1.5 font-bold text-ink">
          <Icon name="calendar" size={16} className="text-ink-3" />
          {formatDate(date)}
          {hours && (
            <span className="font-display text-[15px] font-semibold tabular-nums">{hours}</span>
          )}
        </span>
        {day.sunset && (
          <span className="flex items-center gap-1.5">
            <Icon name="sunset" size={16} className="text-ink-3" />
            Dark from{" "}
            <span className="font-display text-[15px] font-semibold tabular-nums">
              {day.sunset}
            </span>
          </span>
        )}
        {weatherAware && <span>No forecast yet: forecasts reach 5 days ahead.</span>}
      </div>
    );
  }
  return (
    <section
      aria-label={`Weather on ${formatDate(date)}`}
      className="rounded-panel border border-line bg-surface p-3.5"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-control bg-info-soft text-info">
          <Icon name={weatherIcon(forecast)} size={26} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-ink">
            {formatDate(date)}
            {hours && (
              <span className="ml-1.5 font-display text-[15px] font-semibold tabular-nums">
                {hours}
              </span>
            )}
          </p>
          <p className="text-small text-ink-2">
            {sentenceCase(forecast.description)}, {forecast.temp_min_c}–
            {formatTemp(forecast.temp_max_c)}
            {forecast.pop > 0 && `, ${forecast.pop}% chance of rain`}. Daylight {forecast.sunrise}–
            {forecast.sunset}.
          </p>
        </div>
      </div>
      <ol className="mt-3 flex gap-1 overflow-x-auto" aria-label="Forecast by time">
        {forecast.slots.map((slot, i) => (
          // Slots are in time order; a day past midnight can have two of the same clock time.
          <li
            key={i}
            title={slot.description}
            className="flex min-w-14 flex-1 flex-col items-center gap-0.5 rounded-control bg-canvas px-1.5 py-1.5 text-meta text-ink-2"
          >
            <span className="font-display text-[13px] font-semibold tabular-nums">{slot.time}</span>
            <Icon
              name={weatherIcon(slot)}
              size={20}
              label={slot.description}
              className="text-ink"
            />
            <span className="font-bold text-ink tabular-nums">{formatTemp(slot.temp_c)}</span>
            <span
              className={
                slot.pop >= 50 ? "font-bold text-info tabular-nums" : "text-ink-3 tabular-nums"
              }
            >
              {slot.pop}%
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
