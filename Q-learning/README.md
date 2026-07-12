# Q-learning interactive site

A self-contained, no-build, no-server mini-site teaching Q-learning through two live simulators.
Everything is plain HTML/CSS/JS — open any file directly in a browser, no internet required
(except the further-reading links on the home page).

## Files

| File | Purpose |
|---|---|
| `index.html` | Home page: Q-learning primer (agent/environment loop, Bellman equation, exploration vs. exploitation), further-reading links, and two big linked cards to the simulators. |
| `maze.html` | Grid-maze Q-learning simulator. |
| `line-follower.html` | Line-following-robot Q-learning simulator, with a draggable bezier-spline track editor. |

**Keep all three files in the same folder** — the home page links to the other two with relative
paths (`href="maze.html"`, `href="line-follower.html"`), and each simulator links back with
`href="index.html"`.

## Shared design system

Each file repeats the same `:root` CSS variable block (colors, both light and dark via
`prefers-color-scheme`), so they're visually consistent without a shared stylesheet file. If you
add a new page, copy that `:root` block verbatim rather than inventing new colors.

Key variable pairs: `--accent`/`--accent-bg`, `--success`/`--success-bg`, `--danger`/`--danger-bg`,
`--start`/`--start-bg` (green, used for the maze's start marker), `--goal`/`--goal-bg` (amber, used
for the maze's goal marker). Physical/literal colors (the line-follower's red/blue/green track
bands) are hardcoded hex, not theme variables, since they represent real sensor colors, not UI
semantics.

## The shared simulator layout template

Both simulators use the same structural CSS classes, established as the standard template for
**any future simulator added to this site**:

```
.sim-layout        → CSS grid, fixed-width left sidebar + flexible main column
  .sim-sidebar      → sliders (via .sidebar-slider) + reward inputs (via .sidebar-rewards)
  .sim-main-col
    .sim-top-row    → left: mode/action buttons, right: a reset-style button
    .stats-row      → small inline stats
    (the visualization itself — grid or track)
    .sim-action-row → left: a number-box + "Train" button, right: a "test/walk" button
    .status-msg     → single-line feedback text
    .log-panel      → scrolling text log of recent updates
    .q-table        → plain HTML table of Q-values, color-coded (green/red/neutral)
```

`.sim-layout` collapses to a single column below 640px width.

**Convention for the Train control:** a plain `<input type="number">` + "Train" button (not sliders
or scroll wheels — those were tried and replaced per user feedback). Entering exactly `1` triggers
a fully animated single-episode run; anything else trains instantly in the background.

## Maze simulator — implementation notes

- **State space:** every grid cell is its own state (36 cells, 4 actions: up/down/left/right).
  This is the "full" tabular Q-learning case — no simplification needed because the state space is
  already small.
- **Rewards are user-adjustable:** goal reward, wall penalty, step penalty (defaults +10, −1, −0.1).
- **Three click modes**, selected via a segmented control, all dispatched through
  `handleCellClick(i)`: move the goal, move the start, or pick which cell the chart tracks.
- **The tank re-orients** to face whichever direction it just moved, based on the action taken
  (or, during the "walk learned path" replay, inferred from consecutive grid cells).
- **Chart + Q-table:** `qHistory` stores a *full snapshot of the entire Q-table* every episode
  (not just one cell's values) — this is what makes the "track any cell" feature retroactive: you
  can switch which cell the chart displays at any time without needing to retrain, because the full
  history was already recorded. Capped at 2000 episodes to bound memory.
- Moving the **goal** clears `qHistory` (old values described a now-wrong goal). Moving the
  **start** does *not* clear it (history is about the Q-table, not the agent's start position).

## Line-follower simulator — implementation notes, including two real bugs we hit

- **State is the sensor color alone** (red/blue/green → 3 states, 3 actions: turn left/straight/
  right). An earlier version used `(previous color, current color)` — 9 states — on the theory that
  "memory" would help. **It didn't: it made things worse.** Empirically (verified via a standalone
  Python replica of the training loop), the richer state fragmented training data across more
  buckets and diluted the credit-assignment signal, so the agent converged to "go straight while
  centered" — which is wrong on a curving track, since the correct heading is always changing even
  while nominally centered. Dropping back to the plain 3-state design fixed it. **Lesson: adding
  state complexity isn't automatically better; verify empirically.**
- **α and ε decay automatically** as `episodesTrained` grows (`effAlpha()`, `effEps()`), rather than
  staying fixed forever. Without decay, sustained exploration kept perturbing the rarely-visited
  states enough that the greedy policy would flip between correct and broken every so often, even
  after thousands of episodes — verified by training to the same episode count with different
  random seeds and watching success rate swing between 0% and 100%. Decay stabilizes convergence.
- **Track shape:** a Catmull-Rom/Hermite spline through 6 draggable control points, with fixed
  x-positions (only y is draggable). This keeps the track a genuine function of left-to-right
  position — required for the sensor/offset math to stay well-defined — while still rendering as
  real cubic bezier segments (exact Hermite-to-bezier conversion, not a sampled approximation).
  A fully freehand track (arbitrary loops) would need a different physics model entirely.
- Reshaping the track does **not** reset the Q-table on purpose — since the policy is a memoryless
  reaction to color alone, it's a nice demo to train once, reshape the curve, and test whether the
  same policy still holds up without retraining.

## Deliberate non-feature: no shared Q-table between simulators

Asked about early on — worth remembering if it comes up again. The two Q-tables can't be merged or
shared, because they answer different questions over different state/action spaces (grid cell →
direction, vs. sensor color → turn). What *is* shared is the visual language: same table styling,
same chart style, same color coding for "good/bad/neutral" — not the underlying values.

## Extending this site

To add a third simulator:
1. Copy `maze.html` or `line-follower.html` as a starting point (or write fresh HTML using the
   `.sim-layout` structure above).
2. Reuse the `:root` variable block unchanged.
3. Add a `← Back to Q-learning home` link at the top, pointing to `index.html`.
4. Add a new card to the `.sim-cards` grid in `index.html`, with a small inline SVG thumbnail (see
   the existing two cards for the pattern — schematic, few shapes, using the shared CSS variables
   rather than hardcoded UI colors).
