/** @type {import('tailwindcss').Config} */
//
// ChatGPT-inspired dark palette. Notes on each color:
//
//   bg      — the main canvas. ChatGPT runs this just slightly above pure
//             black so subtly-bordered elements on top still register.
//   panel   — the sidebar surface. Pulled darker than `bg` so the boundary
//             reads without needing a visible border line.
//   panel2  — elevated / hover / "selected" surface. Used for the user
//             message bubble, hovered list rows, picker popovers, the
//             composer pill.
//   border  — intentionally near-invisible. ChatGPT uses dividers as a
//             *grouping* signal, not a *containment* one.
//   ink     — primary text (~92% luminance — high but not pure white, which
//             at this size starts to vibrate against the dark canvas).
//   ink2    — secondary text. About 60% luminance.
//   accent  — #10a37f, the ChatGPT signature teal-green. Used sparingly:
//             primary buttons, citation chips, focus rings, the brand mark.
//
// If you want to A/B against the original NVIDIA-green theme, the previous
// palette was: bg #0b0c0f, panel #13151a, panel2 #1a1d24, accent #76b900.
import typography from "@tailwindcss/typography";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#212121",
        panel: "#181818",
        panel2: "#2f2f2f",
        border: "#2f2f2f",
        ink: "#ececec",
        ink2: "#9b9b9b",
        accent: "#10a37f",
        accent2: "#0d8e6e",
        danger: "#ef4444",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  // Required for the `prose` classes used in MessageBubble.tsx — without this
  // plugin those classes are silent no-ops and markdown renders as flat text.
  plugins: [typography],
};
