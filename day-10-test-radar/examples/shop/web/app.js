import { total } from '../shop/../web/lib/money.js';

export function render(cart) {
  return total(cart);
}
