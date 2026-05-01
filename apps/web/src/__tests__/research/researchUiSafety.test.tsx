// Phase 11W (Phase B) — UI safety tests.
//
// NOTE: Vitest + React Testing Library are not yet installed. Tests
// here use the vitest API and JSX rendering helpers; they will
// execute once those packages are added to apps/web/package.json.

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import ResearchBanner from '../../components/research/ResearchBanner';
import ResearchSafetyFailure from '../../components/research/ResearchSafetyFailure';
import ResearchIntelligenceTab from '../../components/research/ResearchIntelligenceTab';
import ResearchPulseCard from '../../components/research/ResearchPulseCard';
import ResearchJobHealthCard from '../../components/research/ResearchJobHealthCard';

describe('ResearchBanner', () => {
  it('renders the frozen banner copy', () => {
    const { getByText } = render(<ResearchBanner context="tab" />);
    expect(getByText(/Research note/i)).toBeTruthy();
    expect(getByText(/not execution logic/i)).toBeTruthy();
    expect(getByText(/not financial advice/i)).toBeTruthy();
  });

  it('throws when context prop is missing at runtime', () => {
    // TS will catch this at compile time; runtime guard backstops.
    expect(() =>
      render(
        // @ts-expect-error -- intentional: simulate missing prop
        <ResearchBanner />,
      ),
    ).toThrow(/context/);
  });
});

describe('ResearchSafetyFailure', () => {
  it('renders the standardised fail-closed message', () => {
    const { getByText } = render(<ResearchSafetyFailure />);
    expect(getByText(/failed safety check/i)).toBeTruthy();
  });
});

describe('Phase B research surfaces — empty-state shells', () => {
  it.each([
    [<ResearchIntelligenceTab key="tab" />, /No research runs yet/i],
    [<ResearchPulseCard key="pulse" />, /0 research runs/i],
    [<ResearchJobHealthCard key="job" />, /disabled \(Phase B\)/i],
  ])('%# renders banner + empty state', (component, emptyMatch) => {
    const { getByText } = render(component);
    expect(getByText(/Research note/i)).toBeTruthy();
    expect(getByText(emptyMatch)).toBeTruthy();
  });

  it('contains zero action-verb buttons across all surfaces', () => {
    const { container } = render(
      <>
        <ResearchIntelligenceTab />
        <ResearchPulseCard />
        <ResearchJobHealthCard />
      </>,
    );
    const buttons = Array.from(container.querySelectorAll('button'));
    const forbidden = /\b(buy|sell|trade|execute|promote|apply)\b/i;
    for (const b of buttons) {
      expect(b.textContent ?? '').not.toMatch(forbidden);
    }
  });
});
