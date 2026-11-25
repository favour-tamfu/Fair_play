"""The meter's private key is stored encrypted with Windows data protection, tied to this computer."""
import binascii
import os

import pytest

from device.tools import provision

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows data protection")


@windows_only
def test_new_key_is_encrypted_and_loads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pub = provision.provision("M-61", "V-BUEA-CIMFEST", force=True)
    text = open(provision.seed_path("M-61"), encoding="ascii").read().strip()
    assert text.startswith("dpapi:")
    seed = provision.load_seed("M-61")
    import base64
    import nacl.signing
    assert base64.b64encode(bytes(nacl.signing.SigningKey(seed).verify_key)).decode() == pub["public_key_b64"]
    assert binascii.hexlify(seed).decode() not in text          # the plain key is not in the file


@windows_only
def test_old_plain_key_still_loads_and_is_encrypted_in_place(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(provision.SECRETS_DIR)
    seed = bytes(range(32))
    with open(provision.seed_path("M-62"), "w", encoding="ascii") as fh:
        fh.write(binascii.hexlify(seed).decode() + "\n")
    assert provision.load_seed("M-62") == seed
    assert open(provision.seed_path("M-62"), encoding="ascii").read().startswith("dpapi:")
    assert provision.load_seed("M-62") == seed


@windows_only
def test_a_damaged_or_foreign_key_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(provision.SECRETS_DIR)
    with open(provision.seed_path("M-63"), "w", encoding="ascii") as fh:
        fh.write("dpapi:" + "QUJD" * 20 + "\n")                  # not made on this computer
    with pytest.raises(OSError):
        provision.load_seed("M-63")
