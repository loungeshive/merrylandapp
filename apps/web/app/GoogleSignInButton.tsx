"use client";

import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";

type GoogleSignInButtonProps = {
  onIdToken: (idToken: string) => void;
  onError: (message: string) => void;
};

export default function GoogleSignInButton({ onIdToken, onError }: GoogleSignInButtonProps) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  if (!clientId) {
    return <p className="google-setup-note">Google sign-in is not configured yet.</p>;
  }

  return (
    <GoogleOAuthProvider clientId={clientId}>
      <div className="google-signin-button">
        <GoogleLogin
          onSuccess={(response) => {
            if (response.credential) onIdToken(response.credential);
            else onError("Google did not return an ID token.");
          }}
          onError={() => onError("Google sign-in failed. Please try again.")}
          theme="outline"
          size="large"
          text="continue_with"
          shape="rectangular"
          width="100%"
        />
      </div>
    </GoogleOAuthProvider>
  );
}
