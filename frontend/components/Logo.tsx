// The brand mark: a question that answers with a chart. Same drawing as app/icon.svg (the favicon).
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <rect width="32" height="32" rx="8" fill="#1d4ed8" />
      <path d="M7 7h18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H14l-5 4v-4H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" fill="#fff" />
      <rect x="10" y="15" width="3.2" height="5" rx="1" fill="#1d4ed8" />
      <rect x="14.4" y="12" width="3.2" height="8" rx="1" fill="#1d4ed8" />
      <rect x="18.8" y="10" width="3.2" height="10" rx="1" fill="#fde047" />
    </svg>
  );
}
