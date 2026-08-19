/** Inline SVG sparkline: min/max normalised polyline with a soft area fill. */
export default function Spark({
  values, width = 120, height = 32, stroke = "#00ff9c", fill = "rgba(0,255,156,0.08)",
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
}) {
  if (values.length < 2) return <svg width={width} height={height} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 2) + 1;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={width} height={height} className="shrink-0">
      <polygon points={`1,${height - 1} ${pts.join(" ")} ${width - 1},${height - 1}`} fill={fill} />
      <polyline points={pts.join(" ")} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}
