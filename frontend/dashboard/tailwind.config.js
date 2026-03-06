/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        tremor: {
          brand: { faint: "#0B1229", muted: "#172554", subtle: "#1e40af", DEFAULT: "#3b82f6", emphasis: "#60a5fa", inverted: "#030712" },
          background: { muted: "#131A2B", subtle: "#1f2937", DEFAULT: "#111827", emphasis: "#d1d5db" },
          border: { DEFAULT: "#1f2937" },
          ring: { DEFAULT: "#1f2937" },
          content: { subtle: "#4b5563", DEFAULT: "#6b7280", emphasis: "#e5e7eb", strong: "#f9fafb", inverted: "#000000" },
        },
      },
    },
  },
  plugins: [],
};
