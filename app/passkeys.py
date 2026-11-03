"""Registrering og innlogging med passkeys (WebAuthn) via biblioteket py_webauthn.

Kravet om brukerverifisering er slått på: det holder ikke at noen har telefonen,
de må også låse den opp med Face ID eller kode.
"""

import json
import secrets
from typing import Any

from sqlmodel import Session, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth import Ugyldig, hash_token, naa
from app.config import Settings
from app.models import Gjenopprettingskode, Passkey

BRUKER_ID = b"dashbord-eier"  # appen har én bruker
APP_NAVN = "Hverdagsdashbord"


def finnes_passkeys(db: Session) -> bool:
    return db.exec(select(Passkey.id).limit(1)).first() is not None


def _alle(db: Session) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=pid) for pid in db.exec(select(Passkey.id)).all()]


# ---------- Registrering ----------


def registreringsvalg(db: Session, settings: Settings) -> tuple[bytes, dict[str, Any]]:
    valg = generate_registration_options(
        rp_id=settings.rp_id,
        rp_name=APP_NAVN,
        user_id=BRUKER_ID,
        user_name="eier",
        user_display_name="Eier",
        exclude_credentials=_alle(db),  # samme enhet kan ikke registreres to ganger
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return valg.challenge, json.loads(options_to_json(valg))


def lagre_passkey(
    db: Session, settings: Settings, credential: dict, challenge: bytes, navn: str
) -> None:
    try:
        verifisert = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.rp_id,
            expected_origin=settings.origin,
            require_user_verification=True,
        )
    except Exception as feil:
        raise Ugyldig("Registreringen kunne ikke bekreftes.") from feil
    db.add(
        Passkey(
            id=verifisert.credential_id,
            offentlig_nokkel=verifisert.credential_public_key,
            signaturteller=verifisert.sign_count,
            navn=navn,
        )
    )
    db.commit()


# ---------- Innlogging ----------


def innloggingsvalg(db: Session, settings: Settings) -> tuple[bytes, dict[str, Any]]:
    valg = generate_authentication_options(
        rp_id=settings.rp_id,
        allow_credentials=_alle(db),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return valg.challenge, json.loads(options_to_json(valg))


def verifiser_innlogging(
    db: Session, settings: Settings, credential: dict, challenge: bytes
) -> Passkey:
    try:
        passkey_id = base64url_to_bytes(str(credential.get("rawId", "")))
    except Exception as feil:
        raise Ugyldig("Innloggingen feilet.") from feil
    passkey = db.get(Passkey, passkey_id)
    if passkey is None:
        raise Ugyldig("Innloggingen feilet.")
    try:
        verifisert = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.rp_id,
            expected_origin=settings.origin,
            credential_public_key=passkey.offentlig_nokkel,
            credential_current_sign_count=passkey.signaturteller,
            require_user_verification=True,
        )
    except Exception as feil:
        raise Ugyldig("Innloggingen feilet.") from feil
    passkey.signaturteller = verifisert.new_sign_count
    passkey.sist_brukt = naa()
    db.add(passkey)
    db.commit()
    return passkey


# ---------- Gjenopprettingskoder ----------

KODE_TEGN = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # uten tegn som er lette å forveksle (0/O, 1/I/L)
ANTALL_KODER = 10


def normaliser_kode(kode: str) -> str:
    return "".join(tegn for tegn in kode.upper() if tegn.isalnum())


def lag_gjenopprettingskoder(db: Session) -> list[str]:
    koder = []
    for _ in range(ANTALL_KODER):
        ra = "".join(secrets.choice(KODE_TEGN) for _ in range(12))
        koder.append(f"{ra[:4]}-{ra[4:8]}-{ra[8:]}")
        db.add(Gjenopprettingskode(kode_hash=hash_token(ra)))
    db.commit()
    return koder


def bruk_gjenopprettingskode(db: Session, kode: str) -> bool:
    lagret = db.get(Gjenopprettingskode, hash_token(normaliser_kode(kode)))
    if lagret is None or lagret.brukt is not None:
        return False
    lagret.brukt = naa()
    db.add(lagret)
    db.commit()
    return True
