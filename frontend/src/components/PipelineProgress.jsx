import { Check, Loader2, Circle, AlertTriangle } from 'lucide-react'

// The backend pipeline (backend/app/services/pipeline.py) emits result.steps
// with exactly these keys; any non-"failed…" value means the step completed
// (catalog_match reports "hit" / "new_part" / "no_part_number").
const STAGES = [
  { key: 'identify', label: 'Identify' },
  { key: 'catalog_match', label: 'Catalog match' },
  { key: 'generate', label: 'Generate' },
  { key: 'assemble', label: 'Assemble' },
]

/**
 * @param {object} props
 * @param {'queued'|'running'|'succeeded'|'failed'} props.jobStatus
 * @param {object} props.steps  result.steps from the pipeline job
 * @param {string} [props.error]
 */
export default function PipelineProgress({ jobStatus, steps, error }) {
  const stageStates = STAGES.map(({ key }, idx) => {
    const value = steps && typeof steps === 'object' ? steps[key] : undefined
    if (typeof value === 'string') {
      return value.startsWith('failed') ? 'failed' : 'done'
    }
    // Step not reported yet: infer from overall job status.
    if (jobStatus === 'succeeded') return 'done'
    if (jobStatus === 'failed') return idx === 0 ? 'failed' : 'pending'
    // queued / running: the first unreported stage is the active one.
    const prevDone = idx === 0 || typeof (steps || {})[STAGES[idx - 1].key] === 'string'
    return prevDone ? 'active' : 'pending'
  })

  return (
    <div className="pipeline">
      <div className="pipeline-head">
        <Loader2 size={16} className={jobStatus === 'running' || jobStatus === 'queued' ? 'spin' : ''} />
        <span>
          {jobStatus === 'queued' && 'Queued…'}
          {jobStatus === 'running' && 'Building your listing…'}
          {jobStatus === 'succeeded' && 'Finishing up…'}
          {jobStatus === 'failed' && 'Pipeline failed'}
          {!jobStatus && 'Working…'}
        </span>
      </div>

      <ol className="pipeline-steps">
        {STAGES.map((stage, i) => {
          const state = stageStates[i]
          return (
            <li key={stage.key} className={`pstep pstep-${state}`}>
              <span className="pstep-icon">
                {state === 'done' && <Check size={16} />}
                {state === 'active' && <Loader2 size={16} className="spin" />}
                {state === 'failed' && <AlertTriangle size={16} />}
                {state === 'pending' && <Circle size={16} />}
              </span>
              <span className="pstep-label">{stage.label}</span>
            </li>
          )
        })}
      </ol>

      {jobStatus === 'failed' && error && (
        <div className="banner banner-error">{error}</div>
      )}
    </div>
  )
}
