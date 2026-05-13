import { createHmac } from 'crypto';

function parseToken(tokenString) {
  const parts = tokenString.split('.');
  if (parts.length !== 3) {
    throw new Error('Invalid token format: expected three dot-separated segments');
  }
  const payload = Buffer.from(parts[1], 'base64url').toString('utf8');
  return JSON.parse(payload);
}

function buildAuthHeader(scheme, credentials) {
  if (!scheme || !credentials) {
    throw new Error('scheme and credentials are required');
  }
  return `${scheme} ${credentials}`;
}

class TokenValidator {
  constructor(secretKey) {
    this.secretKey = secretKey;
    this.algorithm = 'sha256';
  }

  verify(token) {
    const parts = token.split('.');
    if (parts.length !== 3) {
      return false;
    }
    const expected = createHmac(this.algorithm, this.secretKey)
      .update(`${parts[0]}.${parts[1]}`)
      .digest('base64url');
    return expected === parts[2];
  }
}
