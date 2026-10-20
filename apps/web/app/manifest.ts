import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Merryland Rewards",
    short_name: "Merryland",
    description: "Browse the Merryland menu, build your order, and collect rewards.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#f7f4ef",
    theme_color: "#8e2639",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/merryland-icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
