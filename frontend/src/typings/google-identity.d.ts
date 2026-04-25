/**
 * Google Identity Services (GSI) — minimal types for the callback flow.
 * Loaded via https://accounts.google.com/gsi/client
 */
export {};

declare global {
  interface GoogleCredential {
    /** JWT ID token */
    credential: string;
    select_by?: string;
  }

  interface GooglePromptNotification {
    isNotDisplayed: () => boolean;
    isSkippedMoment: () => boolean;
    isDismissedMoment: () => boolean;
    getNotDisplayedReason: () => string;
  }

  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredential) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          prompt: (momentListener?: (notification: GooglePromptNotification) => void) => void;
        };
      };
    };
  }
}
