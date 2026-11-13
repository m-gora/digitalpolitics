// Auth0 Action: inject Gliederung memberships into the ID/access token.
//
// Setup (Auth0 dashboard → Actions → Library → Create Custom Action):
//   1. Paste this code into a "Login" action, trigger: Flow "Login".
//   2. Drag the action into the Login flow AFTER the standard "Add Roles"
//      step (order doesn't strictly matter, but keep it last).
//   3. Deploy.
//
// The claim value is the user's Gliederung membership list, either a single
// slug, an array of slugs, or the literal string "all" (every district):
//
//     app_metadata.gliederungen = "all"
//     app_metadata.gliederungen = ["lv-berlin", "ov-kreuzberg"]
//
// The claim is namespaced with https://dpp/ (Auth0 requires a namespaced
// claim for OIDC tokens). oauth2-proxy reads it via
// OAUTH2_PROXY_OIDC_GROUPS_CLAIM=https://dpp/groups and relays it as
// X-Auth-Request-Groups (see k8s/app/configmap.yaml); the app expands each
// slug to the district and its descendants (adr-03).

/**
 * Handler that will be called during the execution of a Login flow.
 *
 * @param {Event} event - Details about the context and user that triggered the flow.
 * @param {LoginAPI} api - Methods and utilities to help change the behavior of the flow.
 */
exports.onExecutePostLogin = async (event, api) => {
  const gliederungen = event.user.app_metadata?.gliederungen;
  if (!gliederungen || (Array.isArray(gliederungen) && gliederungen.length === 0)) {
    return;
  }
  api.idToken.setCustomClaim("https://dpp/groups", gliederungen);
  api.accessToken.setCustomClaim("https://dpp/groups", gliederungen);
};

/**
 * Handler that will be executed if the post-login action fails.
 *
 * @param {Event} event - Details about the context and user that triggered the flow.
 * @param {PostLoginAPI} api - Methods and utilities to help change the behavior of the flow.
 */
exports.onContinuePostLogin = async (event, api) => {
  console.log("gliederungen claim action failed", event);
};
