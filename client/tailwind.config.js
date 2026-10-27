/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2f5",
          100: "#d9e0e7",
          600: "#3b5b7a",
          700: "#2f4a64",
          800: "#263b50",
        },
      },
    },
  },
  plugins: [],
};