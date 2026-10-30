import jwt
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_refresh_token,
    decode_refresh_token,
)
import pytest
def test_verify_password_ok_and_wrong():
    password = "zheshiyigemima"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    wrong_password = "cuowumima"
    assert verify_password(wrong_password, hashed) is False


def test_password_is_hashed_not_plain():
    password = "zheshiyigemima"
    hashed = hash_password(password)
    assert password != hashed
    hashed_again = hash_password(password)
    assert hashed != hashed_again

def test_access_token_roundtrip():
    user_id = 123456
    access_token = create_access_token(subject = user_id)
    pyload = decode_access_token(access_token)
    assert pyload["sub"] == str(user_id)
    assert "iat" in pyload
    assert "exp" in pyload
    assert pyload["iat"] < pyload["exp"]


def test_malformed_token_rejected():
    really_token = create_access_token(subject=123456)
    fake_token = really_token + "1"
    with pytest.raises(jwt.DecodeError):
        decode_access_token(fake_token)

def test_tampered_token_rejected():
    really_token = create_access_token(subject=123456)
    really_token_list = really_token.split(".")
    payload = really_token_list[1]
    fake_payload = payload[:1] + "X" + payload[2:] if payload[1:2] != "X" else payload[:1] + "Y" + payload[2:]
    fake_token = ".".join([really_token_list[0], fake_payload, really_token_list[2]])

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(fake_token)


def test_refresh_token_type_is_checked():
    access_token = create_access_token(subject=123456)
    with pytest.raises(jwt.InvalidTokenError):
        decode_refresh_token(access_token)
    refresh_token, _, _ = create_refresh_token(subject=123456)
    payload = decode_refresh_token(refresh_token)
    assert payload["type"] == "refresh"
    assert payload["sub"] == "123456"






def test_verify_password_with_garbage_hash():
    garbage_hashs = [
        "",
        "123",
        "sdadas",
        "$213421#@#&$@("
    ]
    password = "123345"
    for garbage_hash in garbage_hashs:
        assert verify_password(password, garbage_hash) is False