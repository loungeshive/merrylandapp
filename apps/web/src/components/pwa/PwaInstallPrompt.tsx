"use client";

import { useEffect, useState } from "react";

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

export default function PwaInstallPrompt() {
  const [installEvent, setInstallEvent] = useState<InstallPromptEvent | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [isIos, setIsIos] = useState(false);
  const [showIosSteps, setShowIosSteps] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch((error: unknown) => {
        console.error("Merryland service worker registration failed.", error);
      });
    }

    const userAgent = window.navigator.userAgent;
    const iosDevice = /iPhone|iPad|iPod/i.test(userAgent)
      || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
    const alreadyInstalled = window.matchMedia("(display-mode: standalone)").matches
      || ("standalone" in window.navigator && window.navigator.standalone === true);

    setIsIos(iosDevice);
    if (!alreadyInstalled && iosDevice) setShowPrompt(true);

    function handleBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      if (alreadyInstalled || window.sessionStorage.getItem("merryland-install-dismissed") === "true") return;
      setInstallEvent(event as InstallPromptEvent);
      setShowPrompt(true);
    }

    function handleAppInstalled() {
      setShowPrompt(false);
      setInstallEvent(null);
    }

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  async function installApp() {
    if (!installEvent) {
      setShowIosSteps(true);
      return;
    }
    try {
      await installEvent.prompt();
      const choice = await installEvent.userChoice;
      if (choice.outcome === "accepted") setShowPrompt(false);
      setInstallEvent(null);
    } catch (error) {
      console.error("Merryland app installation prompt failed.", error);
    }
  }

  function dismissPrompt() {
    window.sessionStorage.setItem("merryland-install-dismissed", "true");
    setShowPrompt(false);
  }

  if (!showPrompt) return null;

  return (
    <aside className="pwa-install-prompt" aria-label="Install Merryland">
      <div className="pwa-install-copy">
        <span className="pwa-install-icon" aria-hidden="true">M</span>
        <div>
          <strong>{showIosSteps ? "Add Merryland to your Home Screen" : "Enjoy Merryland as an app"}</strong>
          <p>
            {showIosSteps
              ? "Tap Share, then choose “Add to Home Screen”."
              : isIos
                ? "Add our menu to your Home Screen for quick access."
                : "Install for quick access to our menu and rewards."}
          </p>
        </div>
      </div>
      <div className="pwa-install-actions">
        {!showIosSteps && (
          <button className="pwa-install-button" type="button" onClick={() => void installApp()}>
            {isIos ? "How to install" : "Install"}
          </button>
        )}
        <button className="pwa-dismiss-button" type="button" onClick={dismissPrompt} aria-label="Dismiss install prompt">
          {showIosSteps ? "Got it" : "Not now"}
        </button>
      </div>
    </aside>
  );
}
