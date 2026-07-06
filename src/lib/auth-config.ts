/**
 * Dev login bypass. Lets you log in without the backend.
 * In production, remove this file or set DEV_LOGIN_ENABLED to false.
 */
export const DEV_LOGIN_ENABLED = false;

export const DEV_CREDENTIALS = {
  username: "admin",
  password: "kabuyedm",
};

export const DEV_USER = {
  id: "dev-admin",
  username: "admin",
  role: "admin" as const,
};

export const DEV_TOKEN = "dev-token-medisoft";

export function isDevCredentials(username: string, password: string) {
  return (
    DEV_LOGIN_ENABLED &&
    username === DEV_CREDENTIALS.username &&
    password === DEV_CREDENTIALS.password
  );
}
