import { describe, expect, it } from 'vitest';
import { isSafeProtocolUrl, placePercentile, placeText } from './fsp';

describe('fsp helpers', () => {
  it('describes place with total', () => {
    expect(placeText(3, 140)).toBe('3 место из 140');
    expect(placeText(2, null)).toBe('2 место');
    expect(placeText(null, 120)).toBeNull();
  });

  it('computes share of participants left behind', () => {
    expect(placePercentile(1, 101)).toBe(100);
    expect(placePercentile(101, 101)).toBe(0);
    expect(placePercentile(11, 101)).toBe(90);
    expect(placePercentile(1, 1)).toBeNull();
  });

  it('allows only web links to protocols', () => {
    expect(isSafeProtocolUrl('https://fsp-registry.example/protocols/EV-1')).toBe(true);
    expect(isSafeProtocolUrl('javascript:alert(1)')).toBe(false);
    expect(isSafeProtocolUrl(null)).toBe(false);
  });
});
