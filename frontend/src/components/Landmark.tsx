/** Original line illustration of a generic domed civic building with trees (decorative; not a depiction of any specific real building). */
export default function Landmark({ className = "" }: { className?: string }) {
  const ink = "#6B5640";
  return (
    <svg viewBox="0 0 240 190" className={className} role="img" aria-label="Decorative illustration of a domed building among trees">
      <g fill="none" stroke={ink} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M120 14v14M114 20h12" />
        <path d="M100 66c0-22 9-36 20-36s20 14 20 36" fill="#F3E7D0" />
        <path d="M106 66c0-16 6-28 14-28s14 12 14 28M120 38v28" />
        <path d="M96 66h48v10H96z" fill="#F3E7D0" />
        <path d="M70 76h100v12H70z" fill="#F3E7D0" />
        <path d="M60 88h120v68H60z" fill="#FBF3E1" />
        {Array.from({ length: 9 }).map((_, i) => <path key={i} d={`M${72 + i * 12} 96v52`} />)}
        <path d="M60 100h120M60 148h120" />
        <path d="M110 156v-26a10 10 0 0 1 20 0v26" fill="#F3E7D0" />
        <path d="M40 156h160M30 164h180" />
        <path d="M64 88V74h10v14M166 88V74h10v14M64 74l5-9 5 9M166 74l5-9 5 9" />
        {Array.from({ length: 8 }).map((_, i) => <path key={i} d={`M${46 + i * 21} 170v6`} opacity=".5" />)}
      </g>
      {[[26, 150, 22], [214, 150, 22], [14, 168, 14], [226, 168, 14]].map(([x, y, r], i) => (
        <g key={i}>
          <path d={`M${x} ${y + r}v${-r * 0.1}`} stroke={ink} strokeWidth="1.5" />
          <circle cx={x} cy={y} r={r} fill="#7A9A7E" opacity=".75" />
          <circle cx={x + r * 0.35} cy={y - r * 0.25} r={r * 0.6} fill="#5E8265" opacity=".7" />
        </g>
      ))}
    </svg>
  );
}
