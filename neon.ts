import { defineConfig } from "@neon/config/v1";

export default defineConfig({
  // Declare your Neon services here
  auth: false,
  // Branch policy: per-branch tuning
  branch: (branch) => {
    if (branch.isDefault) {
      // Keep the account-managed compute defaults, including automatic sleep.
      return {};
    }
    if (!branch.exists) {
      // New non-default branches: auto-expire
      // Run `neon checkout <name> --create` to use these settings
      return { ttl: "7d" };
    }
    // Existing branch: no changes
    return {};
  },
});
