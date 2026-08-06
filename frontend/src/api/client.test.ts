import { describe, expect, it } from 'vitest';

import { ApiError } from './client';

describe('ApiError', () => {
  it('carries the status and code from the response', () => {
    const error = new ApiError(404, 'not_found', 'Project not found.');

    expect(error.status).toBe(404);
    expect(error.code).toBe('not_found');
    expect(error.message).toBe('Project not found.');
    expect(error.name).toBe('ApiError');
    expect(error).toBeInstanceOf(Error);
  });

  describe('isRetryable', () => {
    it.each([
      [0, true], // network failure
      [429, true], // rate limited
      [500, true],
      [503, true],
    ])('treats %i as retryable', (status, expected) => {
      expect(new ApiError(status, 'x', 'y').isRetryable).toBe(expected);
    });

    it.each([[400], [401], [403], [404], [422]])(
      'treats %i as not retryable',
      (status) => {
        expect(new ApiError(status, 'x', 'y').isRetryable).toBe(false);
      },
    );
  });

  describe('validationProblems', () => {
    it('surfaces stack-validation problems', () => {
      const error = new ApiError(422, 'validation_error', 'Invalid stack.', {
        problems: ['FastAPI does not support mongodb.'],
      });

      expect(error.validationProblems).toEqual(['FastAPI does not support mongodb.']);
    });

    it('flattens FastAPI field errors into readable lines', () => {
      const error = new ApiError(422, 'validation_error', 'Failed validation.', {
        errors: [
          { loc: ['body', 'idea'], msg: 'String should have at least 10 characters' },
          { loc: ['body', 'email'], msg: 'value is not a valid email address' },
        ],
      });

      expect(error.validationProblems).toEqual([
        'idea: String should have at least 10 characters',
        'email: value is not a valid email address',
      ]);
    });

    it('returns nothing when the server sent no details', () => {
      expect(new ApiError(500, 'api_error', 'Server error.').validationProblems).toEqual([]);
    });
  });
});
