export default function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#6d28d9" />
      <rect x="6" y="6" width="9" height="9" rx="2.5" fill="#ff5a5f" />
      <rect x="17" y="6" width="9" height="9" rx="2.5" fill="#39b8fd" />
      <rect x="6" y="17" width="9" height="9" rx="2.5" fill="#ffc43d" />
      <rect x="17" y="17" width="9" height="9" rx="2.5" fill="#4edea3" />
    </svg>
  );
}
