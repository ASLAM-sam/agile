import { describe, expect, it } from 'vitest';

import { cn, formatBytes, formatDuration, formatNumber, percent, titleCase, truncate } from './utils';

describe('cn', () => {
  it('joins truthy class names', () => {
    expect(cn('a', 'b')).toBe('a b');
  });

  it('drops falsy values so conditionals stay inline', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b');
  });

  it('returns an empty string when nothing applies', () => {
    expect(cn(false, null)).toBe('');
  });
});

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [1024, '1.0 KB'],
    [1536, '1.5 KB'],
    [1024 * 1024, '1.0 MB'],
  ])('formats %i as %s', (input, expected) => {
    expect(formatBytes(input)).toBe(expected);
  });
});

describe('formatDuration', () => {
  it('renders a dash when there is no duration', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
  });

  it('renders sub-second durations without false precision', () => {
    expect(formatDuration(0.4)).toBe('<1s');
  });

  it('renders seconds and minutes', () => {
    expect(formatDuration(45.2)).toBe('45.2s');
    expect(formatDuration(125)).toBe('2m 5s');
  });
});

describe('formatNumber', () => {
  it('groups thousands', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
  });
});

describe('titleCase', () => {
  it('converts role identifiers to readable labels', () => {
    expect(titleCase('business_analyst')).toBe('Business Analyst');
    expect(titleCase('spring-boot')).toBe('Spring Boot');
  });
});

describe('truncate', () => {
  it('leaves short strings untouched', () => {
    expect(truncate('short', 10)).toBe('short');
  });

  it('adds an ellipsis when it must cut', () => {
    expect(truncate('a very long sentence', 10)).toBe('a very lo…');
    expect(truncate('a very long sentence', 10)).toHaveLength(10);
  });
});

describe('percent', () => {
  it('renders a 0–1 score as a whole percentage', () => {
    expect(percent(0.945)).toBe('95%');
    expect(percent(1)).toBe('100%');
    expect(percent(0)).toBe('0%');
  });
});
