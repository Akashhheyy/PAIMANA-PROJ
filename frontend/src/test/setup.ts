import '@testing-library/jest-dom';

// jsdom does not implement ResizeObserver, which Recharts' ResponsiveContainer needs.
class ResizeObserver {
  observe = () => {}
  unobserve = () => {}
  disconnect = () => {}
}
globalThis.ResizeObserver = ResizeObserver;
