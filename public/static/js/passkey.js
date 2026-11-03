// Innlogging og registrering med passkeys. Ingen inline-skript (CSP), alt ligger her.
"use strict";

(() => {
  const tilBuffer = (tekst) => {
    let s = tekst.replace(/-/g, "+").replace(/_/g, "/");
    s += "===".slice((s.length + 3) % 4);
    return Uint8Array.from(atob(s), (tegn) => tegn.charCodeAt(0)).buffer;
  };
  const tilTekst = (buffer) => {
    let binar = "";
    for (const byte of new Uint8Array(buffer)) binar += String.fromCharCode(byte);
    return btoa(binar).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };

  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content ?? "";

  const vis = (tekst, erFeil = false) => {
    const el = document.getElementById("melding");
    if (!el) return;
    el.textContent = tekst;
    el.classList.toggle("feil", erFeil);
  };

  async function post(url, data) {
    const svar = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(data),
    });
    const json = await svar.json().catch(() => ({}));
    if (!svar.ok) throw new Error(json.feil ?? "Noe gikk galt. Prøv igjen.");
    return json;
  }

  const forklar = (feil) =>
    feil?.name === "NotAllowedError"
      ? "Avbrutt, eller tiden gikk ut. Prøv igjen."
      : (feil?.message ?? "Noe gikk galt. Prøv igjen.");

  const vedlegg = (c) => {
    const ekstra = {};
    if (c.authenticatorAttachment) ekstra.authenticatorAttachment = c.authenticatorAttachment;
    return { id: c.id, rawId: tilTekst(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults?.() ?? {}, ...ekstra };
  };

  // ---------- Innlogging ----------
  const loggInn = document.getElementById("logg-inn-passkey");
  loggInn?.addEventListener("click", async () => {
    loggInn.disabled = true;
    vis("Venter på Face ID …");
    try {
      const { utfordring, valg } = await post("/auth/innlogging/start", {});
      const credential = await navigator.credentials.get({
        publicKey: {
          ...valg,
          challenge: tilBuffer(valg.challenge),
          allowCredentials: (valg.allowCredentials ?? []).map((k) => ({ ...k, id: tilBuffer(k.id) })),
        },
      });
      const r = credential.response;
      const svar = await post("/auth/innlogging/fullfor", {
        utfordring,
        credential: {
          ...vedlegg(credential),
          response: {
            clientDataJSON: tilTekst(r.clientDataJSON),
            authenticatorData: tilTekst(r.authenticatorData),
            signature: tilTekst(r.signature),
            userHandle: r.userHandle ? tilTekst(r.userHandle) : null,
          },
        },
      });
      window.location.assign(svar.neste);
    } catch (feil) {
      vis(forklar(feil), true);
      loggInn.disabled = false;
    }
  });

  // ---------- Registrering ----------
  const skjema = document.getElementById("registrer-skjema");
  skjema?.addEventListener("submit", async (hendelse) => {
    hendelse.preventDefault();
    const knapp = skjema.querySelector("button");
    knapp.disabled = true;
    vis("Venter på Face ID …");
    const felt = new FormData(skjema);
    const setupToken = felt.get("setup_token") || null;
    const navn = String(felt.get("navn") || "iPhone");
    try {
      const { utfordring, valg } = await post("/auth/registrering/start", { setup_token: setupToken });
      const credential = await navigator.credentials.create({
        publicKey: {
          ...valg,
          challenge: tilBuffer(valg.challenge),
          user: { ...valg.user, id: tilBuffer(valg.user.id) },
          excludeCredentials: (valg.excludeCredentials ?? []).map((k) => ({ ...k, id: tilBuffer(k.id) })),
        },
      });
      const r = credential.response;
      const svar = await post("/auth/registrering/fullfor", {
        utfordring,
        navn,
        setup_token: setupToken,
        credential: {
          ...vedlegg(credential),
          response: {
            clientDataJSON: tilTekst(r.clientDataJSON),
            attestationObject: tilTekst(r.attestationObject),
            transports: r.getTransports?.() ?? [],
          },
        },
      });
      if (svar.koder) {
        const liste = document.getElementById("kodeliste");
        for (const kode of svar.koder) {
          const li = document.createElement("li");
          li.textContent = kode; // textContent, ikke innerHTML
          liste.append(li);
        }
        document.getElementById("registrering").hidden = true;
        document.getElementById("koder").hidden = false;
      } else {
        window.location.assign(svar.neste);
      }
    } catch (feil) {
      vis(forklar(feil), true);
      knapp.disabled = false;
    }
  });
})();
