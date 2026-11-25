import { render } from '../app.js';

test('renders a cart', () => {
  expect(render({ items: [] })).toBe(0);
});

it.skip('renders empty', () => {});
