/** Complete a kit whose program already exists but whose seed was interrupted before policy/merchants/hooks/actors. */
import { KitApiClient } from "./lib/client";
import { assertHackathonOrg } from "./lib/org-guard";
import { writeKitState, type SeededActor, type SeededMerchant } from "./lib/state";
import { actorPrivyUserId, programSlugFor } from "./lib/synthetic";
import { resolveMerchantRefs } from "./lib/resolve-refs";
import { loadManifest } from "./seed-kit";

async function main() {
  const kit = process.argv[2];
  const manifest = loadManifest(kit);
  const client = new KitApiClient({ baseUrl: process.env.API_BASE_URL!, apiKey: process.env.HACKATHON_ORG_API_KEY! });
  const org = await assertHackathonOrg(client);
  const slug = programSlugFor(manifest.program.slugPrefix, org.id);
  let prog: { program: { id: string; policies?: unknown[] } };
  try {
    prog = await client.get<{ program: { id: string; policies?: unknown[] } }>(`/programs/${slug}`);
  } catch (e: any) {
    if (e?.status !== 404) throw e;
    const created = await client.post<{ program: { id: string } }>("/programs", { slug, name: `${manifest.program.name} (${org.name})`, currency: manifest.program.currency, currencySymbol: manifest.program.currencySymbol, balanceModel: manifest.program.balanceModel, backingType: manifest.program.backingType, settings: manifest.program.settings });
    console.log(`✔ program ${slug} created (${created.program.id})`);
    prog = { program: { id: created.program.id, policies: [] } };
  }
  const programId = prog.program.id;
  console.log(`program ${slug} (${programId}), policies: ${JSON.stringify(prog.program.policies).slice(0, 80)}`);
  if (!prog.program.policies || (prog.program.policies as unknown[]).length === 0) {
    const policyRes = await client.post<{ policy: { id: string } }>("/policy", { name: `${manifest.title} Policy`, programId });
    await client.put(`/policy/${policyRes.policy.id}`, { tiers: manifest.policy.tiers, eligibilityRules: manifest.policy.eligibilityRules, categories: manifest.policy.categories });
    await client.post(`/policy/${policyRes.policy.id}/activate`);
    console.log("✔ policy created + activated");
  }
  const merchants: SeededMerchant[] = []; const merchantIdByRef: Record<string, string> = {};
  for (const m of manifest.merchants) {
    const res = await client.post<{ merchant: { id: string; name: string } }>("/merchants/register", { name: m.name, approvedCategories: m.approvedCategories });
    await client.post(`/merchants/${res.merchant.id}/assign`, { programId });
    merchants.push({ ref: m.ref, id: res.merchant.id, name: res.merchant.name }); merchantIdByRef[m.ref] = res.merchant.id;
    console.log(`✔ merchant ${m.ref} ${res.merchant.id}`);
  }
  const hooks: Array<{ name: string; id: string }> = [];
  for (const h of manifest.hooks) {
    const ruleConfig = h.ruleConfig ? resolveMerchantRefs(h.ruleConfig, merchantIdByRef) : undefined;
    const res = await client.post<{ hook: { id: string } }>(`/programs/${slug}/hooks`, { event: h.event, phase: h.phase, name: h.name, description: h.description ?? "", type: h.type, ruleConfig, actionConfig: h.actionConfig, actionType: h.type === "rate_limit" ? "rate_limit" : "gate", effect: h.effect, failureBehavior: h.failureBehavior });
    hooks.push({ name: h.name, id: res.hook.id }); console.log(`✔ hook ${h.name}`);
  }
  const actors: SeededActor[] = []; const mandateIdByRef: Record<string, string> = {};
  for (const actor of manifest.actors) {
    const privyUserId = actorPrivyUserId(manifest.kitId, org.id, actor.ref);
    const enrol = await client.post<{ beneficiary: { id: string; tokenId: number } }>(`/programs/${slug}/self-enrol`, { privyUserId, fields: { ...actor.fields, phone: actor.phone } });
    let mandateId: string | undefined, mandateKeyPrefix: string | undefined;
    if (actor.mandate) {
      const parent = actor.mandate.parentRef ? mandateIdByRef[actor.mandate.parentRef] : undefined;
      const res = await client.post<{ id: string; keyPrefix: string }>(parent ? `/ai-vouchers/${parent}/child` : "/ai-vouchers", { label: actor.mandate.label, policy: actor.mandate.policy ?? {}, metadata: { kitId: manifest.kitId, orgId: org.id, actorRef: actor.ref } });
      mandateId = res.id; mandateKeyPrefix = res.keyPrefix; mandateIdByRef[actor.ref] = res.id;
    }
    actors.push({ ref: actor.ref, beneficiaryId: enrol.beneficiary.id, tokenId: enrol.beneficiary.tokenId, privyUserId, mandateId, mandateKeyPrefix });
    console.log(`✔ actor ${actor.ref} enrolled, mandate ${mandateId}`);
  }
  writeKitState({ kitId: manifest.kitId, orgId: org.id, programId, programSlug: slug, merchants, actors, hooks, seededAt: new Date().toISOString() });
  console.log(`state written: artifacts/kits/${manifest.kitId}-${org.id}.json`);
}
main().catch((e) => { console.error(e); process.exit(1); });
