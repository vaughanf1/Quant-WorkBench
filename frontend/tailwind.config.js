/** Amber/black terminal palette carried over from BB-Terminal. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        term: {
          bg: "#0a0a0a",
          bg2: "#111111",
          panel: "#141414",
          panel2: "#1a1a1a",
          border: "#2a2a2a",
          borderSoft: "#1f1f1f",
          text: "#d0d0d0",
          heading: "#f0f0f0",
          muted: "#6e6e6e",
          amber: "#ff8c00",
          amberDim: "#a55f00",
          amberBright: "#ffaa33",
          amberSubtle: "rgba(255,140,0,0.08)",
          green: "#22ee22",
          greenDim: "#128812",
          red: "#ff3b3b",
          redDim: "#9a1414",
          cyan: "#22ccee",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: { panel: "0 0 0 1px #1f1f1f, 0 8px 30px rgba(0,0,0,0.4)" },
    },
  },
  plugins: [],
};
