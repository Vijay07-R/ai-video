/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0c0b09", 900: "#14120f", 850: "#1b1814", 800: "#24201a", 700: "#332d24", 600: "#4a4235" },
        sand: { 100: "#f6efe3", 200: "#e9dcc5", 300: "#d4c2a1", 400: "#a8987c" },
        mane: { 300: "#ffcf7a", 400: "#f7b548", 500: "#e8962a", 600: "#c4741a" },
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
