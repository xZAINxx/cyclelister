const LABELS = {
  draft: 'Draft',
  pending_review: 'Needs review',
  listed: 'Listed',
  ended: 'Ended',
  sold: 'Sold',
  error: 'Error',
}

export default function StatusBadge({ status }) {
  const label = LABELS[status] || status || 'Unknown'
  return <span className={`badge badge-${status || 'unknown'}`}>{label}</span>
}
