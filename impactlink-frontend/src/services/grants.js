const DEMO_GRANT_IDS = new Set([
  "357797",
  "334326",
  "356690",
  "355900",
  "348500",
]);

export function removeDemoGrants(grants) {
  if (!Array.isArray(grants)) return [];
  return grants.filter(grant => !DEMO_GRANT_IDS.has(String(grant.grant_id)));
}
