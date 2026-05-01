// Phase 11W (Phase B) - fail-closed render block. Displayed in place
// of any research artifact body whose contents fail the client-side
// token guard. Wording is FROZEN.

export interface ResearchSafetyFailureProps {
  // The matched forbidden token (for ops review, never user-facing
  // detail beyond a generic notice).
  matched?: string;
}

export default function ResearchSafetyFailure(_: ResearchSafetyFailureProps) {
  return (
    <div
      role="alert"
      aria-label="Research safety failure"
      className="research-safety-failure"
      style={{
        backgroundColor: '#fafafa',
        border: '1px solid #bdbdbd',
        borderRadius: 4,
        color: '#424242',
        fontSize: 13,
        padding: '12px 16px',
      }}
    >
      <strong>⚠ </strong>
      Research note rejected — content failed safety check.
    </div>
  );
}
