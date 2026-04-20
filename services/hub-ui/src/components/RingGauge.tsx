import { useEffect, useRef } from 'react';

// ── Threshold helpers ────────────────────────────────────────────────────────

type GaugeColor = 'success' | 'warning' | 'danger' | 'info' | 'muted';

function colorVar(c: GaugeColor): string {
  switch (c) {
    case 'success': return 'var(--status-success)';
    case 'warning': return 'var(--status-warning)';
    case 'danger':  return 'var(--status-danger)';
    case 'info':    return 'var(--status-info)';
    default:        return 'var(--ink-muted)';
  }
}

/** Map a 0–1 ratio to a semantic colour based on configurable thresholds. */
export function gaugeColor(
  ratio: number,
  opts: { warnBelow?: number; dangerBelow?: number; invert?: boolean } = {},
): GaugeColor {
  const { warnBelow = 0.5, dangerBelow = 0.25, invert = false } = opts;
  const r = invert ? 1 - ratio : ratio;
  if (r >= 0.8) return 'success';
  if (r >= warnBelow) return 'warning';
  if (r >= dangerBelow) return 'danger';
  return 'danger';
}

// ── RingGauge ────────────────────────────────────────────────────────────────

interface RingGaugeProps {
  /** 0 – 1, proportion filled */
  ratio: number;
  size?: number;
  strokeWidth?: number;
  color: GaugeColor;
  /** Optional small label inside the ring */
  label?: string;
  /** Duration of the fill animation in ms */
  animDuration?: number;
}

export default function RingGauge({
  ratio,
  size = 72,
  strokeWidth = 6,
  color,
  label,
  animDuration = 800,
}: RingGaugeProps) {
  const circleRef = useRef<SVGCircleElement>(null);
  const clamped   = Math.min(1, Math.max(0, ratio));
  const r         = (size - strokeWidth) / 2;
  const circ      = 2 * Math.PI * r;
  const cx        = size / 2;
  const accent    = colorVar(color);

  // Animate stroke-dashoffset from full (empty ring) → target
  useEffect(() => {
    const el = circleRef.current;
    if (!el) return;

    const target = circ * (1 - clamped);
    // Start from empty
    el.style.transition = 'none';
    el.style.strokeDashoffset = String(circ);

    // Defer one frame so the "none" transition takes effect
    const raf = requestAnimationFrame(() => {
      el.style.transition = `stroke-dashoffset ${animDuration}ms cubic-bezier(0.4, 0, 0.2, 1)`;
      el.style.strokeDashoffset = String(target);
    });

    return () => cancelAnimationFrame(raf);
  }, [clamped, circ, animDuration]);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ display: 'block', overflow: 'visible' }}
    >
      {/* Track */}
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke="var(--line-strong)"
        strokeWidth={strokeWidth}
        opacity={0.3}
      />

      {/* Glow layer (subtle) */}
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={accent}
        strokeWidth={strokeWidth + 4}
        strokeDasharray={`${circ} ${circ}`}
        strokeDashoffset={circ * (1 - clamped)}
        strokeLinecap="round"
        opacity={0.08}
        transform={`rotate(-90 ${cx} ${cx})`}
      />

      {/* Progress arc */}
      <circle
        ref={circleRef}
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={accent}
        strokeWidth={strokeWidth}
        strokeDasharray={`${circ} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cx})`}
      />

      {/* Centre label */}
      {label !== undefined && (
        <text
          x={cx}
          y={cx}
          textAnchor="middle"
          dominantBaseline="central"
          style={{
            fontSize: size * 0.22,
            fontWeight: 700,
            fill: accent,
            fontFamily: 'Inter, sans-serif',
          }}
        >
          {label}
        </text>
      )}
    </svg>
  );
}
