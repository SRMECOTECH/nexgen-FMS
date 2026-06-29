# UI Guide — design system & page recipe

How the redesigned frontend is put together, and how to roll the same
**visuals-first + paginated** pattern onto the remaining pages.

---

## 1. Typography

Loaded in `frontend/index.html` from Google Fonts:

- **Space Grotesk** → headings & metrics. Applied automatically to `h1/h2/h3`,
  and via the `.font-display` / `.metric` / `.tabular` utility classes.
- **Inter** → body text (the default `body` font).

Tokens live in `src/index.css`:

```css
--font-body:    'Inter', system-ui, sans-serif;
--font-display: 'Space Grotesk', 'Inter', system-ui, sans-serif;
```

Use `.metric` (or `.tabular`) on any number you want rendered with tabular,
tracking-tight display figures (KPI values, counts, pagination ranges).

## 2. Theme tokens

All colors are CSS variables in `src/index.css` (`:root`). Accent is cyan/sky/sea-blue.
Never hardcode hex in components — use `var(--accent)`, `var(--fg-2)`, etc.
Semantic: `--success --warning --danger --info`. Surfaces: `--bg-0..3`.

Reusable classes added this pass: `.input-field`, `.btn-soft`, `.row-hover`,
plus the existing `.card`, `.card-hover`, `.chip`, `.btn-primary`, `.text-gradient`.

## 3. Components

### KPI tile — `components/ui/KpiCard`
```tsx
<KpiCard index={0} icon={Truck} label="Trucks" value={42}
         tone="success" trend="3 stale" delta={12} />
```
`tone`: `default | success | warning | danger`. `delta` renders a ▲/▼ change chip.
`index` staggers the entrance animation. Put 4–6 in a responsive grid.

### Chart frame — `components/charts/ChartCard`
Titled card wrapper for any chart. `icon`, `subtitle`, `right` (toolbar slot), `delay`.

### Charts — `components/charts/*` (Recharts, pre-themed)
```tsx
<DonutChart data={[{name,value,color?}]} centerValue={total} centerLabel="trips" />
<BarChart   data={[{label,value,color?}]} horizontal highlightMax unit=" km" />
<AreaTrend  data={rows} xKey="date" yKey="pings" unit="" />
<Gauge      value={onTimePct} label="on time" />          // 0..100, auto red/amber/green
```
Shared palette + themed tooltip live in `components/charts/theme.tsx` (`SERIES`,
`ChartTooltip`, `AXIS`, `GRID`). New charts should reuse these so everything matches.

### Pagination — `hooks/usePagination` + `components/ui/Pagination`
```tsx
const paged = usePagination(rows, 12);        // 12 rows/page
// render paged.pageItems instead of rows
<Pagination state={paged} label="trips" />
```
`usePagination` is client-side: it slices an in-memory array and re-clamps the page
when the data shrinks (e.g. after a filter), so you never land on an empty page.
For server-paged endpoints, drive `state.page` into the request instead.

## 4. The visuals-first page recipe

Every operational page follows the same vertical order:

```
PageHeader (title + Refresh/Upload actions)
   ↓
KPI row            ← 4–6 <KpiCard> in a grid
   ↓
Charts row         ← 2–3 <ChartCard> (donut / ranked bars / gauge / trend)  ← the highlight
   ↓
Filters + table    ← search/chips, then a <table>, then <Pagination>
```

Derive chart data **client-side** from the payload you already fetch (see
`Dashboard.tsx` / `Trips.tsx` `useMemo` blocks) — no extra endpoints needed for
distributions and top-N rankings.

## 5. Why native charts (not Streamlit)

Streamlit is a separate Python web server; the only way to "embed" it in React is an
`<iframe>`. That means a second process to run/deploy, a theme that won't match the
cyan dark UI, and **no shared state** (filters, selected vehicle, open trip can't sync).
The diagrams you liked are just Plotly/Altair under the hood — Recharts (already a
dependency) reproduces them natively, themed and interactive, with none of that cost.

## 6. Rolling out to the remaining pages

Done: **Dashboard, Trips, GPS Feed**. To convert another page:

1. Wrap the title row in `PageHeader` (move Refresh/Upload into `actions`).
2. Replace ad-hoc stat boxes with a `<KpiCard>` grid.
3. Add a charts row: pick `DonutChart` for a status/category split, `BarChart horizontal`
   for top-N, `Gauge` for a percentage, `AreaTrend` for a time series. Build the data
   with `useMemo` over the existing fetch.
4. Swap any `maxHeight`-scroll table for `usePagination` + `<Pagination>`.
5. Keep colors as theme vars; numbers get `.metric`/`.tabular`.

Good next candidates: **Partners, Behavioural Patterns, Lane Volume, Halts & Rests,
Monitoring, Pipelines, Data Quality** — each already has tabular data and a natural
chart (party volumes, hour-of-day heatmaps, lane bars, halt-reason donuts).
