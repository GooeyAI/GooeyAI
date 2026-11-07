export default {
  SERVER_HOST: process.env.SERVER_HOST || "http://127.0.0.1:8080",
  REDIS_URL: process.env.REDIS_URL,
  SENTRY_DSN: process.env.SENTRY_DSN,
  SENTRY_RELEASE: process.env.SENTRY_RELEASE,
  // Font Awesome Pro kit url. Unset (the default) serves Font Awesome Free.
  FONTAWESOME_KIT_URL: process.env.FONTAWESOME_KIT_URL || "",
};
