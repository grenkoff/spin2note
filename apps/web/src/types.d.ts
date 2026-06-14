import "react";

// Allow the non-standard folder-picker attributes on <input> for bulk uploads.
declare module "react" {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: string;
    directory?: string;
  }
}
