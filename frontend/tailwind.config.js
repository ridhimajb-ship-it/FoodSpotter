/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAF5EA",      // warm cream page
        card: "#FFFFFF",
        ink: "#2A2420",        // charcoal text
        muted: "#6B5E54",      // secondary text (5.4:1 on paper)
        line: "#EADFC9",
        sidebar: "#FCF8EF",
        chili: { DEFAULT: "#B8441C", dark: "#93350F", soft: "#F6DFD2" },   // terracotta/orange accent
        leaf: { DEFAULT: "#1E4D3B", dark: "#143628", soft: "#DCE9E1" },    // deep green
        saffron: { DEFAULT: "#E9A23B", soft: "#FBEBCB" },
        pos: "#2E7D4F", neg: "#B3382C", neu: "#8A7F73",
      },
      fontFamily: {
        display: ['"Playfair Display Variable"', "Georgia", "ui-serif", "serif"],
        script: ['"Caveat"', "cursive"],
        sans: ['"Instrument Sans Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: { lift: "0 1px 0 #E6DAC4, 0 8px 24px -12px rgba(42,36,32,.25)", soft: "0 1px 2px rgba(60,40,20,.05), 0 6px 18px -10px rgba(60,40,20,.18)" },
    },
  },
  plugins: [],
};
